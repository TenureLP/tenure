"""JSON-RPC client over urllib, with the one distinction that matters: a call that reverted is not
the same thing as a call that never reached the chain.

Conflating the two is how a service ends up telling people their position does not exist when the
real answer is that the upstream node timed out.
"""

import json
import random
import threading
import time
import urllib.error
import urllib.request

MAX_BODY = 32 << 20  # a well-formed answer is never this big; a hostile one should not be buffered
RETRIES = 3
TIMEOUT = 8.0
# Node error messages that mean "the call itself failed on chain", as opposed to "we could not ask".
REVERT_HINTS = ("revert", "invalid opcode", "out of gas", "stack underflow")


class RpcError(Exception):
    """The node answered, and the answer was an error."""


class UpstreamError(Exception):
    """We never got a usable answer: timeout, transport failure, rate limit, garbage."""


REVERTED = object()  # the call itself failed on chain, which is a real answer
UNAVAILABLE = object()  # we never got an answer for this item


class Rpc:
    def __init__(self, url: str, timeout: float = TIMEOUT):
        if not url.startswith("https://") and not url.startswith("http://localhost"):
            raise ValueError("the RPC url must be https (or a localhost node)")
        self.url = url
        self.timeout = timeout
        self._id = 0
        # urllib follows redirects by default; an RPC endpoint has no business redirecting us.
        self._opener = urllib.request.build_opener(_NoRedirect)
        self._local = threading.local()

    # ------------------------------------------------------------------ deadline

    def set_deadline(self, seconds: float) -> None:
        """Bound everything this thread is about to ask for. One inbound request makes several
        dependent round trips, each of which may retry; without a shared ceiling their budgets
        multiply and a single request can hold a worker for minutes."""
        self._local.until = time.monotonic() + seconds

    def clear_deadline(self) -> None:
        self._local.until = None

    def _remaining(self):
        until = getattr(self._local, "until", None)
        return None if until is None else until - time.monotonic()

    # ------------------------------------------------------------------ transport

    def _post_once(self, payload):
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"content-type": "application/json", "user-agent": "lpval/0.2"},
        )
        left = self._remaining()
        if left is not None and left <= 0:
            raise UpstreamError("deadline exceeded before the request was sent")
        timeout = self.timeout if left is None else min(self.timeout, left)
        with self._opener.open(req, timeout=timeout) as resp:
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
            left = self._remaining()
            if left is not None and left <= 0:
                raise UpstreamError("deadline exceeded")
            if attempt + 1 < RETRIES:
                pause = (0.25 * 2**attempt) * (1 + random.random())
                time.sleep(pause if left is None else min(pause, max(0.0, left)))
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

    @staticmethod
    def _item_result(item):
        """A JSON-RPC item becomes its result, REVERTED if the chain rejected the call, or
        UNAVAILABLE if the node could not answer. Collapsing the last two is how a rate-limited
        node ends up telling a user their position does not exist."""
        if not isinstance(item, dict):
            return UNAVAILABLE
        if "error" in item:
            message = ""
            err = item["error"]
            if isinstance(err, dict):
                message = str(err.get("message", "")).lower()
                if err.get("code") == 3:  # the conventional code for a revert with return data
                    return REVERTED
            return REVERTED if any(h in message for h in REVERT_HINTS) else UNAVAILABLE
        return item.get("result")

    def batch(self, reqs):
        """reqs: list of (method, params). Returns results in order, each being the value, REVERTED
        or UNAVAILABLE. Raises UpstreamError if we never got a usable response at all."""
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
                    results.append(REVERTED)
            return results
        by_id = {}
        for item in out:
            if isinstance(item, dict):
                by_id[item.get("id")] = item
        return [self._item_result(by_id.get(p["id"])) for p in payload]

    def eth_calls(self, calls, block="latest"):
        """calls: list of (to, data_hex). Each result is bytes, or REVERTED when the node answered
        that the call failed. A transport failure raises instead of pretending the call reverted."""
        tag = block if isinstance(block, str) else hex(block)
        raw = self.batch([("eth_call", [{"to": to, "data": data}, tag]) for to, data in calls])
        out = []
        for r in raw:
            if r is UNAVAILABLE:
                raise UpstreamError("the node did not answer an eth_call")
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
