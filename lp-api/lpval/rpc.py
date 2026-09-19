"""JSON-RPC client over urllib, with the one distinction that matters: a call that reverted is not
the same thing as a call that never reached the chain.

Conflating the two is how a service ends up telling people their position does not exist when the
real answer is that the upstream node timed out.

Several endpoints can be given. They are tried in order, not spread round-robin: providers sit at
slightly different heights, and a batch read at "latest" landing on a node a few blocks behind the
one that just gave us a block number reads state that does not match it. The order is a preference,
and the rest are what the first one falls back to.
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
# HTTP codes worth asking the same endpoint about again. Anything else is the endpoint telling us
# something about itself, a bad key or a wrong path, so we move on rather than repeat it.
RETRYABLE_HTTP = (408, 425, 429, 500, 502, 503, 504)


class RpcError(Exception):
    """The node answered, and the answer was an error."""


class UpstreamError(Exception):
    """We never got a usable answer: timeout, transport failure, rate limit, garbage."""


REVERTED = object()  # the call itself failed on chain, which is a real answer
UNAVAILABLE = object()  # we never got an answer for this item


class Endpoint:
    """One node, and whatever it needs to let us in.

    Authentication differs by provider and both shapes are secret: some put a key in the url path,
    others want a header. Neither belongs in a log line or an error message, so `label` is the only
    part of an endpoint that is ever safe to print.
    """

    __slots__ = ("url", "headers", "label")

    # Plaintext is allowed to a node on this machine and nowhere else: there is no network for
    # anyone to listen on. Matched on the host rather than on the prefix, because
    # http://localhost.example.com starts with http://localhost and is somebody else’s server.
    LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")

    def __init__(self, url, headers=None):
        if not url.startswith("https://") and not self._is_local(url):
            raise ValueError("the RPC url must be https (or a node on this machine)")
        self.url = url
        self.headers = dict(headers or {})
        self.label = url.split("://", 1)[1].split("/", 1)[0]  # host only, so no key

    @classmethod
    def _is_local(cls, url):
        if not url.startswith("http://"):
            return False
        host = url[len("http://"):].split("/", 1)[0].split("?", 1)[0]
        if "@" in host:  # user:password@elsewhere, which is not this machine
            return False
        return host in cls.LOCAL_HOSTS or host.rsplit(":", 1)[0] in cls.LOCAL_HOSTS

    def secrets(self):
        """The parts of this endpoint that must never appear in text we emit."""
        out = []
        tail = self.url.rstrip("/").rsplit("/", 1)[-1]
        # The last path segment is the key for Alchemy, Infura and most of the others. A bare
        # hostname is not worth redacting, and doing so would mangle ordinary messages.
        if len(tail) > 8 and tail != self.label:
            out.append(tail)
        out.extend(v for v in self.headers.values() if len(v) > 8)
        return out

    def __repr__(self):
        return "<Endpoint " + self.label + ">"


def parse_endpoints(spec):
    """Reads an endpoint list.

    Entries are separated by whitespace, because a url never contains any and a header value might
    contain a comma. Each entry is a url, optionally followed by headers:

        https://a.example/v2/KEY  https://b.example|x-api-key:SECRET
    """
    if isinstance(spec, Endpoint):
        return [spec]
    entries = spec.split() if isinstance(spec, str) else list(spec)

    out = []
    for entry in entries:
        if isinstance(entry, Endpoint):
            out.append(entry)
            continue
        url, *raw_headers = str(entry).split("|")
        headers = {}
        for item in raw_headers:
            if ":" not in item:
                raise ValueError("an endpoint header must be written name:value")
            name, value = item.split(":", 1)
            headers[name.strip()] = value.strip()
        out.append(Endpoint(url.strip(), headers))
    if not out:
        raise ValueError("at least one RPC endpoint is required")
    return out


class Rpc:
    def __init__(self, url, timeout=TIMEOUT):
        self.endpoints = parse_endpoints(url)
        self.url = self.endpoints[0].url  # the preferred one, for callers that want a single name
        self.timeout = timeout
        self._id = 0
        self._id_lock = threading.Lock()
        # urllib follows redirects by default; an RPC endpoint has no business redirecting us.
        self._opener = urllib.request.build_opener(_NoRedirect)
        self._local = threading.local()

    def describe(self):
        """What may be said about the endpoints out loud, in a log line or a banner."""
        return ", ".join(e.label for e in self.endpoints)

    def scrub(self, text):
        """Takes the endpoints back out of a message before it can escape.

        Error text reaches callers: a failed fee-rate probe reports its reason on a public route.
        The key lives in the url for some providers and in a header for others, and nothing
        upstream promises not to quote back what it was given.
        """
        out = text
        for endpoint in self.endpoints:
            out = out.replace(endpoint.url, "the RPC endpoint")
            for secret in endpoint.secrets():
                out = out.replace(secret, "[redacted]")
        return out

    def _next_id(self):
        """Ids must be unique within a payload; an unlocked increment can hand two threads the same
        one and collapse two results into one."""
        with self._id_lock:
            self._id += 1
            return self._id

    # ------------------------------------------------------------------ deadline

    def set_deadline(self, seconds):
        """Bound everything this thread is about to ask for. One inbound request makes several
        dependent round trips, each of which may retry; without a shared ceiling their budgets
        multiply and a single request can hold a worker for minutes."""
        self._local.until = time.monotonic() + seconds

    def clear_deadline(self):
        self._local.until = None

    def _remaining(self):
        until = getattr(self._local, "until", None)
        return None if until is None else until - time.monotonic()

    # ------------------------------------------------------------------ transport

    def _post_once(self, payload, endpoint):
        headers = {"content-type": "application/json", "user-agent": "lpval/0.2"}
        headers.update(endpoint.headers)
        req = urllib.request.Request(endpoint.url, data=json.dumps(payload).encode(), headers=headers)
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
            raise UpstreamError(self.scrub("response was not JSON: " + str(exc))) from exc

    def _post(self, payload, endpoints=None):
        """Retries idempotent reads. Every JSON-RPC method this client sends is a read."""
        eps = list(endpoints or self.endpoints)
        last = None
        dead = set()  # endpoints that answered something no repetition will fix
        attempts = max(RETRIES, len(eps))
        for attempt in range(attempts):
            endpoint = eps[attempt % len(eps)]
            if endpoint.label in dead:
                continue
            try:
                return self._post_once(payload, endpoint)
            except urllib.error.HTTPError as exc:
                last = UpstreamError("HTTP " + str(exc.code) + " from " + endpoint.label)
                if exc.code not in RETRYABLE_HTTP:
                    # A refusal about this endpoint itself. Another one may still be fine, so keep
                    # going rather than failing the whole read over one bad key.
                    dead.add(endpoint.label)
                    if len(dead) >= len(eps):
                        raise last from exc
            except UpstreamError as exc:
                last = exc
            except Exception as exc:  # timeout, DNS, reset, TLS
                last = UpstreamError(self.scrub(str(exc)))
            left = self._remaining()
            if left is not None and left <= 0:
                raise UpstreamError("deadline exceeded")
            if attempt + 1 >= attempts:
                break
            # Moving to a different endpoint is itself the mitigation, so only wait when the next
            # attempt would ask something we have already asked.
            if attempt + 1 >= len(eps):
                pause = (0.25 * 2**attempt) * (1 + random.random())
                time.sleep(pause if left is None else min(pause, max(0.0, left)))
        raise last or UpstreamError("upstream unavailable")

    # ------------------------------------------------------------------ calls

    def request(self, method, params):
        out = self._post({"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params})
        if not isinstance(out, dict):
            raise UpstreamError("expected a single JSON-RPC response")
        if "error" in out:
            raise RpcError(self.scrub(method + ": " + str(out["error"])))
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

    def batch(self, reqs, endpoints=None):
        """reqs: list of (method, params). Returns results in order, each being the value, REVERTED
        or UNAVAILABLE. Raises UpstreamError if we never got a usable response at all."""
        if not reqs:
            return []
        payload = []
        for method, params in reqs:
            payload.append({"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params})
        out = self._post(payload, endpoints)
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

    @staticmethod
    def _decode_calls(raw):
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

    def eth_calls(self, calls, block="latest", persist=False):
        """calls: list of (to, data_hex). Each result is bytes, or REVERTED when the node answered
        that the call failed. A transport failure raises instead of pretending the call reverted.

        `persist` re-asks the other endpoints when a node answers that it cannot serve the state.
        That answer is about one node, not about the chain: a provider fronting a pool serves
        historical state from some of its nodes and not others, so one refusal is not evidence that
        the history is gone. Without it, the same position gets a different fee rate depending on
        which node happened to pick up the request, and a rent is quoted off that.
        """
        tag = block if isinstance(block, str) else hex(block)
        reqs = [("eth_call", [{"to": to, "data": data}, tag]) for to, data in calls]
        if not persist:
            return self._decode_calls(self.batch(reqs))

        last = None
        count = len(self.endpoints)
        for offset in range(count * 2):
            turn = offset % count
            rotated = self.endpoints[turn:] + self.endpoints[:turn]
            try:
                return self._decode_calls(self.batch(reqs, rotated))
            except UpstreamError as exc:
                last = exc
            left = self._remaining()
            if left is not None and left <= 0:
                break
        raise last or UpstreamError("no endpoint could serve the call")

    def block_number(self):
        head = self.request("eth_blockNumber", [])
        if not isinstance(head, str):
            raise UpstreamError("eth_blockNumber did not return a quantity")
        return int(head, 16)

    def block_timestamp(self, number):
        blk = self.request("eth_getBlockByNumber", [hex(number), False])
        if not isinstance(blk, dict) or "timestamp" not in blk:
            raise UpstreamError("block " + str(number) + " unavailable")
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
