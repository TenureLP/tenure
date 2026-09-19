"""HTTP API. Standard library only.

Routes
  GET     /health
  OPTIONS /v1/position/<tokenId>            CORS preflight, needed for the payment headers
  GET     /v1/position/<tokenId>            valuation        (paid when the paywall is enabled)
  GET     /v1/position/<tokenId>/quote      valuation + indicative sale-and-leaseback terms (paid)
      ?term=7&haircut=0.2&rentShare=0.5&lookbackHours=24
"""

import json
import re
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .paywall import Paywall
from .rpc import Rpc, UpstreamError
from .valuation import CHAIN_ID, RPC_URL, PositionNotFound, quote, value_position

_ROUTE = re.compile(r"^/v1/position/(\d{1,78})(/quote)?/?$")
_MAX_TOKEN_ID = 2**256 - 1
_CACHE_TTL = 3.0
_CACHE_MAX = 5000
_CONCURRENCY = 64

_cache = OrderedDict()
_cache_lock = threading.Lock()
_inflight = {}
_slots = threading.Semaphore(_CONCURRENCY)


def _num(qs, key, default, lo, hi, cast=float):
    try:
        v = cast(qs.get(key, [default])[0])
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return max(lo, min(hi, v))


def _cached(key, build):
    """One valuation per key at a time. Without this, twenty people opening the same position
    produce twenty identical round trips to the node and rate-limit us against ourselves."""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            _cache.move_to_end(key)
            return hit[1]
        event = _inflight.get(key)
        leader = event is None
        if leader:
            event = threading.Event()
            _inflight[key] = event
    if not leader:
        event.wait(timeout=30)
        with _cache_lock:
            hit = _cache.get(key)
        if hit:
            return hit[1]
        # The leader failed; fall through and try once ourselves rather than inventing an error.
    try:
        value = build()
        with _cache_lock:
            _cache[key] = (time.time(), value)
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
        return value
    finally:
        with _cache_lock:
            if _inflight.get(key) is event:
                del _inflight[key]
        event.set()


def make_handler(rpc: Rpc, paywall: Paywall):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"lpval/{__version__}"
        protocol_version = "HTTP/1.1"
        timeout = 15

        def _send(self, status: int, body: dict, extra_headers=None):
            raw = json.dumps(body, indent=2).encode()
            try:
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.send_header("access-control-allow-origin", "*")
                self.send_header(
                    "access-control-expose-headers", "PAYMENT-REQUIRED, PAYMENT-RESPONSE, WWW-Authenticate"
                )
                for k, v in (extra_headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
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

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/health":
                return self._send(200, {"ok": True, "version": __version__, "chainId": CHAIN_ID, "paywall": paywall.enabled})

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
                self._serve(url, m, token_id)
            finally:
                _slots.release()

        def _serve(self, url, m, token_id):
            paid_headers, spent_hash = {}, None
            if paywall.enabled:
                # Display only. Nothing is ever signed over the Host header, which the caller sets.
                host = self.headers.get("Host") or ""
                challenge = paywall.challenge(url.path, f"http://{host}" if host else "")
                required = {"PAYMENT-REQUIRED": paywall.encode(challenge), "WWW-Authenticate": "x402"}
                try:
                    proof, err = paywall.parse_proof(self.headers)
                    if err or proof is None:
                        if err:
                            challenge["reason"] = err
                        return self._send(402, challenge, required)
                    ok, reason, receipt = paywall.verify(proof, url.path)
                except Exception:
                    return self._send(402, dict(challenge, reason="the proof could not be read"), required)
                if not ok:
                    challenge["reason"] = reason
                    return self._send(402, challenge, required)
                spent_hash = proof["txHash"]
                paid_headers = {"PAYMENT-RESPONSE": paywall.encode(receipt)}

            qs = parse_qs(url.query)
            lookback = int(_num(qs, "lookbackHours", 24.0, 0.0, 720.0))
            try:
                val = _cached((token_id, lookback), lambda: value_position(rpc, token_id, lookback_hours=lookback))
            except PositionNotFound as exc:
                if spent_hash:
                    paywall.release(spent_hash)  # they paid for an answer we could not give
                return self._send(404, {"error": "position_not_found", "detail": str(exc)})
            except (UpstreamError, Exception):
                if spent_hash:
                    paywall.release(spent_hash)
                return self._send(502, {"error": "upstream_error", "message": "the chain could not be read right now"})

            if m.group(2):
                val = dict(val)
                val["quote"] = quote(
                    val,
                    term_days=_num(qs, "term", 7, 1, 30, int),
                    haircut=_num(qs, "haircut", 0.20, 0.0, 0.9),
                    rent_share=_num(qs, "rentShare", 0.5, 0.0, 1.0),
                )
            return self._send(200, val, paid_headers)

        def log_message(self, fmt, *args):
            # A request line is attacker-controlled; never let it write raw bytes to a terminal.
            line = (fmt % args).encode("unicode_escape").decode()
            print(f"{self.address_string()} {line}")

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8402):
    rpc = Rpc(RPC_URL)
    paywall = Paywall(rpc, CHAIN_ID)
    httpd = ThreadingHTTPServer((host, port), make_handler(rpc, paywall))
    print(f"lpval {__version__} on http://{host}:{port}  rpc={RPC_URL}  paywall={'on' if paywall.enabled else 'off'}")
    httpd.serve_forever()
