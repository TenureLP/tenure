"""HTTP API. Standard library only.

Routes
  GET /health
  GET /v1/position/<tokenId>            valuation        (paid when the paywall is enabled)
  GET /v1/position/<tokenId>/quote      valuation + indicative sale-and-leaseback terms (paid)
      ?term=7&haircut=0.2&rentShare=0.5&lookbackHours=24
"""

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .paywall import Paywall
from .rpc import Rpc
from .valuation import CHAIN_ID, RPC_URL, PositionNotFound, quote, value_position

_ROUTE = re.compile(r"^/v1/position/(\d{1,78})(/quote)?/?$")
_CACHE_TTL = 3.0
_cache = {}


def _num(qs, key, default, lo, hi, cast=float):
    try:
        v = cast(qs.get(key, [default])[0])
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def make_handler(rpc: Rpc, paywall: Paywall):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"lpval/{__version__}"

        def _send(self, status: int, body: dict, extra_headers=None):
            raw = json.dumps(body, indent=2).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.send_header("access-control-allow-origin", "*")
            for k, v in (extra_headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/health":
                return self._send(200, {"ok": True, "version": __version__, "chainId": CHAIN_ID, "paywall": paywall.enabled})

            m = _ROUTE.match(url.path)
            if not m:
                return self._send(404, {"error": "not_found"})

            paid_headers = {}
            if paywall.enabled:
                challenge = paywall.challenge(url.path)
                required = {"PAYMENT-REQUIRED": paywall.encode(challenge)}
                tx, payer, err = paywall.parse_proof(self.headers)
                if err or not tx:
                    if err:
                        challenge["reason"] = err
                    return self._send(402, challenge, required)
                ok, reason, receipt = paywall.verify(tx, url.path, payer)
                if not ok:
                    challenge["reason"] = reason
                    return self._send(402, challenge, required)
                paid_headers = {"PAYMENT-RESPONSE": paywall.encode(receipt)}

            token_id, want_quote = int(m.group(1)), bool(m.group(2))
            qs = parse_qs(url.query)
            lookback = _num(qs, "lookbackHours", 24.0, 0.0, 24.0 * 30)
            key = (token_id, lookback)
            try:
                hit = _cache.get(key)
                if hit and time.time() - hit[0] < _CACHE_TTL:
                    val = hit[1]
                else:
                    val = value_position(rpc, token_id, lookback_hours=lookback)
                    _cache[key] = (time.time(), val)
            except PositionNotFound as exc:
                return self._send(404, {"error": "position_not_found", "detail": str(exc)})
            except Exception as exc:
                return self._send(502, {"error": "upstream_error", "detail": str(exc)})

            if want_quote:
                val = dict(val)
                val["quote"] = quote(
                    val,
                    term_days=_num(qs, "term", 7, 1, 30, int),
                    haircut=_num(qs, "haircut", 0.20, 0.0, 0.9),
                    rent_share=_num(qs, "rentShare", 0.5, 0.0, 1.0),
                )
            return self._send(200, val, paid_headers)

        def log_message(self, fmt, *args):  # quieter logs
            print(f"{self.address_string()} {fmt % args}")

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8402):
    rpc = Rpc(RPC_URL)
    paywall = Paywall(rpc, CHAIN_ID)
    httpd = ThreadingHTTPServer((host, port), make_handler(rpc, paywall))
    print(f"lpval {__version__} on http://{host}:{port}  rpc={RPC_URL}  paywall={'on' if paywall.enabled else 'off'}")
    httpd.serve_forever()
