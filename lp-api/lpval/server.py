"""HTTP API. Standard library only.

Routes
  GET     /health
  GET     /openapi.yaml                     the machine-readable description of everything below
  GET     /openapi.json                     the same document, for tooling that will not take YAML
  HEAD    any of the above                  the same headers, no body
  OPTIONS /v1/position/<tokenId>            CORS preflight, needed for the payment headers
  GET     /v1/position/<tokenId>            valuation        (paid when the paywall is enabled)
  GET     /v1/position/<tokenId>/quote      valuation + indicative sale-and-leaseback terms (paid)
      ?term=7&haircut=0.2&rentShare=0.5&lookbackHours=24
  GET     /v1/owner/<address>/positions     every position a wallet holds, valued and diagnosed (paid)
      ?lookbackHours=24
"""

import json
import os
import re
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .paywall import Paywall
from .portfolio import portfolio
from .rpc import Rpc, UpstreamError
from .valuation import CHAIN_ID, RPC_URL, PositionNotFound, quote, value_position

_ROUTE = re.compile(r"^/v1/position/(\d{1,78})(/quote)?/?$")
_OWNER_ROUTE = re.compile(r"^/v1/owner/(0x[0-9a-fA-F]{40})/positions/?$")
_PORTFOLIO_TTL = 30.0  # a wallet is dozens of valuations; nobody's positions change twice a minute
_PORTFOLIO_BUDGET = 40.0
_MAX_TOKEN_ID = 2**256 - 1
_CACHE_TTL = 3.0
_CACHE_MAX = 5000
_CONCURRENCY = 64

_cache = OrderedDict()
_cache_lock = threading.Lock()
_inflight = {}
_slots = threading.Semaphore(_CONCURRENCY)
_BUILD_BUDGET = 25.0  # wall clock a single valuation may spend upstream

# Served from the running instance rather than a wiki, so the description cannot drift from the
# build that answers. Read once; it is a few kilobytes and it never changes while the process runs.
_SPEC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC_FILES = {
    "/openapi.yaml": ("openapi.yaml", "application/yaml; charset=utf-8"),
    "/openapi.yml": ("openapi.yaml", "application/yaml; charset=utf-8"),
    "/openapi.json": ("openapi.json", "application/json; charset=utf-8"),
}
_spec_cache = {}
_spec_lock = threading.Lock()


class _Flight:
    """One in-progress build. Followers read its outcome instead of repeating the work, and get the
    leader's exception rather than a stale value or a stampede."""

    __slots__ = ("event", "value", "exc")

    def __init__(self):
        self.event = threading.Event()
        self.value = None
        self.exc = None


def _spec(name):
    """This service's own OpenAPI document, read once per spelling."""
    with _spec_lock:
        if name not in _spec_cache:
            try:
                with open(os.path.join(_SPEC_DIR, name), "rb") as fh:
                    _spec_cache[name] = fh.read()
            except OSError:
                _spec_cache[name] = b""
        return _spec_cache[name]


def _num(qs, key, default, lo, hi, cast=float):
    try:
        v = cast(qs.get(key, [default])[0])
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return max(lo, min(hi, v))


def _cached(key, build, ttl=_CACHE_TTL):
    """One valuation per key at a time. Without this, twenty people opening the same position
    produce twenty identical round trips to the node and rate-limit us against ourselves.

    A follower never falls back to building on its own: when the leader fails, every waiter would
    then build at once, which is a stampede at exactly the moment the upstream is already in
    trouble. They get the leader's exception instead. And a follower never reads the cache, so a
    stale entry can never be served as if it were fresh.
    """
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            _cache.move_to_end(key)
            return hit[1]
        flight = _inflight.get(key)
        leader = flight is None
        if leader:
            flight = _Flight()
            _inflight[key] = flight

    if not leader:
        if not flight.event.wait(timeout=max(_BUILD_BUDGET, _PORTFOLIO_BUDGET) + 5):
            raise UpstreamError("timed out waiting for a valuation already in flight")
        if flight.exc is not None:
            raise flight.exc
        return flight.value

    try:
        flight.value = build()
        with _cache_lock:
            _cache[key] = (time.time(), flight.value)
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
        return flight.value
    except Exception as exc:
        # Deliberately not BaseException: a KeyboardInterrupt stored here would be re-raised in
        # unrelated threads that never asked to be interrupted.
        flight.exc = exc
        raise
    finally:
        # Only the leader may retire its own flight, and it is the only one that can reach here.
        with _cache_lock:
            if _inflight.get(key) is flight:
                del _inflight[key]
        flight.event.set()


def make_handler(rpc: Rpc, paywall: Paywall):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"lpval/{__version__}"
        protocol_version = "HTTP/1.1"
        timeout = 15

        def _send(self, status: int, body: dict, extra_headers=None):
            self._send_raw(status, json.dumps(body, indent=2).encode(), "application/json", extra_headers)

        def _send_raw(self, status: int, raw: bytes, content_type: str, extra_headers=None):
            try:
                self.send_response(status)
                self.send_header("content-type", content_type)
                self.send_header("content-length", str(len(raw)))
                self.send_header("access-control-allow-origin", "*")
                self.send_header(
                    "access-control-expose-headers", "PAYMENT-REQUIRED, PAYMENT-RESPONSE, WWW-Authenticate"
                )
                for k, v in (extra_headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                # A HEAD carries every header a GET would, and no body. Content-length still
                # describes what a GET would have returned, which is what HEAD is for.
                if not getattr(self, "_head_only", False):
                    self.wfile.write(raw)
            except (ConnectionError, BrokenPipeError):
                pass  # the client went away mid-response; that is not a fault worth logging

        def do_OPTIONS(self):  # noqa: N802
            # Without this the browser never sends the payment header at all.
            self.send_response(204)
            self.send_header("access-control-allow-origin", "*")
            self.send_header("access-control-allow-methods", "GET, OPTIONS")
            self.send_header(
                "access-control-allow-headers", "payment-signature, x402-payment, authorization, content-type"
            )
            self.send_header(
                "access-control-expose-headers", "PAYMENT-REQUIRED, PAYMENT-RESPONSE, WWW-Authenticate"
            )
            self.send_header("access-control-max-age", "86400")
            self.send_header("content-length", "0")
            self.end_headers()

        def do_HEAD(self):  # noqa: N802
            # Without this the base class answers 501, and validators, link checkers and CDNs all
            # ask with HEAD before they ask with GET. Same work, same headers, no body: anything
            # cheaper would have to guess at the status it is reporting.
            self._head_only = True
            try:
                self.do_GET()
            finally:
                self._head_only = False

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/health":
                return self._send(200, {"ok": True, "version": __version__, "chainId": CHAIN_ID, "paywall": paywall.enabled})

            # Never priced. A client has to be able to read what it is being asked to pay for
            # before it can decide to pay for it.
            spec = _SPEC_FILES.get(url.path)
            if spec:
                body = _spec(spec[0])
                if not body:
                    return self._send(404, {"error": "not_found"})
                return self._send_raw(200, body, spec[1])

            owner = _OWNER_ROUTE.match(url.path)
            if owner:
                if not _slots.acquire(blocking=False):
                    return self._send(503, {"error": "busy", "message": "too many requests in flight"}, {"retry-after": "2"})
                try:
                    rpc.set_deadline(_PORTFOLIO_BUDGET)
                    self._serve_owner(url, owner.group(1).lower())
                finally:
                    rpc.clear_deadline()
                    _slots.release()
                return

            m = _ROUTE.match(url.path)
            if not m:
                return self._send(404, {"error": "not_found"})
            token_id = int(m.group(1))
            if token_id > _MAX_TOKEN_ID:
                return self._send(404, {"error": "not_found"})

            if not _slots.acquire(blocking=False):
                # Honest refusal beats accepting work we cannot do.
                return self._send(503, {"error": "busy", "message": "too many requests in flight"}, {"retry-after": "2"})
            try:
                # One budget for the whole request, payment verification included, and cleared after.
                # A thread serves every request of a keep-alive connection, so a deadline left behind
                # would refuse the next one before it even reached the node.
                rpc.set_deadline(_BUILD_BUDGET)
                self._serve(url, m, token_id)
            finally:
                rpc.clear_deadline()
                _slots.release()

        def _pay(self, resource):
            """None when the request may proceed, with the receipt headers and what was spent; or
            the response already sent when it may not."""
            if not paywall.enabled:
                return {}, None, False
            host = self.headers.get("Host") or ""
            challenge = paywall.challenge(resource, f"http://{host}" if host else "")
            required = {"PAYMENT-REQUIRED": paywall.encode(challenge), "WWW-Authenticate": "x402"}
            try:
                proof, err = paywall.parse_proof(self.headers)
                if err or proof is None:
                    if err:
                        challenge["reason"] = err
                    self._send(402, challenge, required)
                    return None, None, True
                ok, reason, receipt = paywall.verify(proof, resource)
            except Exception:
                self._send(402, dict(challenge, reason="the proof could not be read"), required)
                return None, None, True
            if not ok:
                challenge["reason"] = reason
                self._send(402, challenge, required)
                return None, None, True
            return {"PAYMENT-RESPONSE": paywall.encode(receipt)}, (proof["txHash"], proof["payer"], resource), False

        def _serve_owner(self, url, owner):
            qs = parse_qs(url.query)
            lookback = int(_num(qs, "lookbackHours", 24.0, 0.0, 720.0))
            paid_headers, spent, answered = self._pay(f"{url.path}?lookbackHours={lookback}")
            if answered:
                return
            try:
                body = _cached(("owner", owner, lookback), lambda: portfolio(rpc, owner, lookback), _PORTFOLIO_TTL)
            except Exception:
                if spent:
                    paywall.release(*spent)
                return self._send(502, {"error": "upstream_error", "message": "the chain could not be read right now"})
            return self._send(200, body, paid_headers)

        def _serve(self, url, m, token_id):
            qs = parse_qs(url.query)
            lookback = int(_num(qs, "lookbackHours", 24.0, 0.0, 720.0))
            terms = (
                _num(qs, "term", 7, 1, 30, int),
                _num(qs, "haircut", 0.20, 0.0, 0.9),
                _num(qs, "rentShare", 0.5, 0.0, 1.0),
            )
            # What the payer signs has to name the work, not just the path: `lookbackHours` drives
            # how much upstream work a request costs, so leaving it out of the signature would let
            # one payment buy the cheapest request and then be replayed against the dearest.
            resource = f"{url.path}?lookbackHours={lookback}"

            paid_headers, spent = {}, None
            if paywall.enabled:
                # Display only. Nothing is ever signed over the Host header, which the caller sets.
                host = self.headers.get("Host") or ""
                challenge = paywall.challenge(resource, f"http://{host}" if host else "")
                required = {"PAYMENT-REQUIRED": paywall.encode(challenge), "WWW-Authenticate": "x402"}
                try:
                    proof, err = paywall.parse_proof(self.headers)
                    if err or proof is None:
                        if err:
                            challenge["reason"] = err
                        return self._send(402, challenge, required)
                    ok, reason, receipt = paywall.verify(proof, resource)
                except Exception:
                    return self._send(402, dict(challenge, reason="the proof could not be read"), required)
                if not ok:
                    challenge["reason"] = reason
                    return self._send(402, challenge, required)
                spent = (proof["txHash"], proof["payer"], resource)
                paid_headers = {"PAYMENT-RESPONSE": paywall.encode(receipt)}

            try:
                val = _cached((token_id, lookback), lambda: value_position(rpc, token_id, lookback_hours=lookback))
            except PositionNotFound as exc:
                # A token id the caller chose and that does not exist is a real answer, so the
                # payment stands. Refunding here would let one payment buy unlimited failed work.
                return self._send(404, {"error": "position_not_found", "detail": str(exc)})
            except Exception:
                if spent:
                    paywall.release(*spent)  # our fault, so they can retry, once, with the same proof
                return self._send(502, {"error": "upstream_error", "message": "the chain could not be read right now"})

            if m.group(2):
                val = dict(val)
                val["quote"] = quote(val, term_days=terms[0], haircut=terms[1], rent_share=terms[2])
            return self._send(200, val, paid_headers)

        def log_message(self, fmt, *args):
            # A request line is attacker-controlled; never let it write raw bytes to a terminal.
            line = (fmt % args).encode("unicode_escape").decode()
            print(f"{self.address_string()} {line}")

    return Handler


def serve(host: str = None, port: int = None):
    """Binds to 127.0.0.1 for local work, and to every interface when a platform hands us a PORT.

    A container that listens on loopback is invisible to the proxy in front of it, which is the
    single most common way a first deployment looks like it started and answers nothing.
    """
    env_port = os.environ.get("PORT")
    if port is None:
        port = int(env_port) if env_port else 8402
    if host is None:
        host = os.environ.get("HOST") or ("0.0.0.0" if env_port else "127.0.0.1")

    rpc = Rpc(RPC_URL)
    paywall = Paywall(rpc, CHAIN_ID)
    if paywall.enabled and not _storage_is_durable():
        raise SystemExit(
            "The paywall is on but its ledger is not on a durable path.\n"
            "Spent payments would be forgotten whenever the container is replaced, and every one of\n"
            "them could then be redeemed a second time. Point LPVAL_DB at a mounted volume, or\n"
            "unset LPVAL_PAY_TO to run free."
        )
    httpd = ThreadingHTTPServer((host, port), make_handler(rpc, paywall))
    print(
        # Hosts only. The url carries the key for most providers, and this line goes to a log that
        # is kept, shipped and read by people who have no business holding it.
        f"lpval {__version__} on http://{host}:{port}  rpc={rpc.describe()}  "
        f"paywall={'on' if paywall.enabled else 'off'}",
        flush=True,
    )
    httpd.serve_forever()


def _storage_is_durable() -> bool:
    """True when the payment ledger lives somewhere that survives a restart.

    Locally any path counts. On a platform that replaces containers, it has to be under a mount the
    operator declared, which we take to be LPVAL_DATA_DIR.
    """
    if not os.environ.get("PORT"):
        return True
    data_dir = os.environ.get("LPVAL_DATA_DIR")
    db = os.environ.get("LPVAL_DB", "")
    return bool(data_dir) and db.startswith(data_dir)
