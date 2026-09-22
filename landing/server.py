"""Serves the landing in production. Same handler as the local preview, bound the way a container
needs, and with the headers every public page here carries.

    python server.py            local, 127.0.0.1:8410
    PORT=8080 python server.py  container
"""

import os
import sys
from functools import partial
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dev_server import Handler  # noqa: E402

CSP = "; ".join([
    "default-src 'none'",
    # The pages run no script at all. The mobile menu is a <details> element.
    "script-src 'none'",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data:",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
])


class ProdHandler(Handler):
    def end_headers(self):
        self.send_header("content-security-policy", CSP)
        self.send_header("x-frame-options", "DENY")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("referrer-policy", "strict-origin-when-cross-origin")
        self.send_header("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("strict-transport-security", "max-age=31536000")
        super().end_headers()

    def log_message(self, fmt, *args):
        # The path and the status, never the visitor's address.
        sys.stderr.write("%s\n" % (fmt % args))

    def address_string(self):
        return "-"


def main():
    env_port = os.environ.get("PORT")
    port = int(env_port) if env_port else 8410
    # Loopback is invisible to the proxy in front of a container, which is the usual reason a first
    # deployment reports itself healthy and answers nothing.
    host = os.environ.get("HOST") or ("0.0.0.0" if env_port else "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), partial(ProdHandler, directory=HERE))
    print(f"landing on http://{host}:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
