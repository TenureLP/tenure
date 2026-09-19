"""JSON-RPC client over urllib, with the one distinction that matters: a call that reverted is not
the same thing as a call that never reached the chain.

Conflating the two is how a service ends up telling people their position does not exist when the
real answer is that the upstream node timed out.
"""

import json
import random
import time
import urllib.error
import urllib.request

MAX_BODY = 32 << 20  # a well-formed answer is never this big; a hostile one should not be buffered
RETRIES = 3
TIMEOUT = 8.0


class RpcError(Exception):
    """The node answered, and the answer was an error."""


class UpstreamError(Exception):
    """We never got a usable answer: timeout, transport failure, rate limit, garbage."""


REVERTED = object()  # sentinel: the call itself failed on chain, which is a real answer


class Rpc:
    def __init__(self, url: str, timeout: float = TIMEOUT):
        if not url.startswith("https://") and not url.startswith("http://localhost"):
            raise ValueError("the RPC url must be https (or a localhost node)")
        self.url = url
        self.timeout = timeout
        self._id = 0
        # urllib follows redirects by default; an RPC endpoint has no business redirecting us.
        self._opener = urllib.request.build_opener(_NoRedirect)

    # ------------------------------------------------------------------ transport

    def _post_once(self, payload):
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json", "user-agent": "lpval/0.2"},
        )
        with self._opener.open(req, timeout=self.timeout) as resp:
            body = resp.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise UpstreamError("response too large")
        try:
            return json.loads(body)
        except ValueError as exc:
            raise UpstreamError(f"response was not JSON: {exc}") from exc

    def _post(self, payload):
        """Retries idempotent reads. Every JSON-RPC method this client sends is a read."""
        last = None
        for attempt in range(RETRIES):
            try:
                return self._post_once(payload)
            except urllib.error.HTTPError as exc:
                last = UpstreamError(f"HTTP {exc.code}")
                if exc.code not in (408, 425, 429, 500, 502, 503, 504):
                    raise last from exc
            except UpstreamError as exc:
                last = exc
            except Exception as exc:  # timeout, DNS, reset, TLS
                last = UpstreamError(str(exc))
            if attempt + 1 < RETRIES:
                time.sleep((0.25 * 2**attempt) * (1 + random.random()))
        raise last or UpstreamError("upstream unavailable")

    # ------------------------------------------------------------------ calls

    def request(self, method: str, params: list):
        self._id += 1
        out = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        if not isinstance(out, dict):
            raise UpstreamError("expected a single JSON-RPC response")
        if "error" in out:
            raise RpcError(f"{method}: {out['error']}")
        return out.get("result")

    def batch(self, reqs):
        """reqs: list of (method, params). Returns results in order; an item the node answered with
        an error is None. Raises UpstreamError if we never got a usable response at all."""
        if not reqs:
            return []
        payload = []
        for method, params in reqs:
            self._id += 1
            payload.append({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        out = self._post(payload)
        if not isinstance(out, list):
            # A node that genuinely does not implement batching: fall back once, sequentially.
            # Never do this after a transport failure, which would multiply the load on a node that
            # is already struggling.
            results = []
            for method, params in reqs:
                try:
                    results.append(self.request(method, params))
                except RpcError:
                    results.append(None)
            return results
        by_id = {}
        for item in out:
            if isinstance(item, dict):
                by_id[item.get("id")] = item
        return [by_id.get(p["id"], {}).get("result") for p in payload]

    def eth_calls(self, calls, block="latest"):
        """calls: list of (to, data_hex). Each result is bytes, or REVERTED when the node answered
        that the call failed. A transport failure raises instead of pretending the call reverted."""
        tag = block if isinstance(block, str) else hex(block)
        raw = self.batch([("eth_call", [{"to": to, "data": data}, tag]) for to, data in calls])
        out = []
        for r in raw:
            if isinstance(r, str) and r.startswith("0x"):
                try:
                    out.append(bytes.fromhex(r[2:]))
                    continue
                except ValueError:
                    pass
            out.append(REVERTED)
        return out

    def block_number(self) -> int:
        head = self.request("eth_blockNumber", [])
        if not isinstance(head, str):
            raise UpstreamError("eth_blockNumber did not return a quantity")
        return int(head, 16)

    def block_timestamp(self, number: int) -> int:
        blk = self.request("eth_getBlockByNumber", [hex(number), False])
        if not isinstance(blk, dict) or "timestamp" not in blk:
            raise UpstreamError(f"block {number} unavailable")
        return int(blk["timestamp"], 16)

    def head_block(self):
        """Number and timestamp of the head in one round trip instead of two."""
        blk = self.request("eth_getBlockByNumber", ["latest", False])
        if not isinstance(blk, dict):
            raise UpstreamError("latest block unavailable")
        return int(blk["number"], 16), int(blk["timestamp"], 16)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
