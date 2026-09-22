"""Serves the built documentation. Standard library only, like every other server here.

    npm run build && python3 server.py      local, 127.0.0.1:8430
    PORT=8080 python3 server.py             container

VitePress builds with clean urls, so /guide/testnet is the file guide/testnet.html. Only files inside
the build directory can be served, and nothing else in this folder is in it.
"""

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.environ.get("DOCS_DIST") or os.path.join(HERE, ".vitepress", "dist")

CSP = "; ".join([
    "default-src 'none'",
    # VitePress inlines a small script that applies the colour scheme before first paint.
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: https:",
    "connect-src 'self'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
])


class Handler(SimpleHTTPRequestHandler):
    timeout = 15

    def translate_path(self, path):
        full = super().translate_path(path)
        # A clean url names the page without its extension.
        if not os.path.exists(full) and os.path.exists(full + ".html"):
            return full + ".html"
        return full

    def send_error(self, code, message=None, explain=None):
        page = os.path.join(DIST, "404.html")
        if code == 404 and os.path.exists(page):
            with open(page, "rb") as f:
                body = f.read()
            self.send_response(404)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)

    def end_headers(self):
        path = self.path.split("?", 1)[0]
        # Hashed assets never change under the same name; pages do.
        cache = "public, max-age=31536000, immutable" if path.startswith("/assets/") else "no-cache"
        self.send_header("cache-control", cache)
        self.send_header("content-security-policy", CSP)
        self.send_header("x-frame-options", "DENY")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("referrer-policy", "no-referrer")
        self.send_header("strict-transport-security", "max-age=31536000")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))

    def address_string(self):
        return "-"


def main():
    if not os.path.isdir(DIST):
        raise SystemExit("no build at %s: run `npm run build` first" % DIST)
    env_port = os.environ.get("PORT")
    port = int(env_port) if env_port else 8430
    host = os.environ.get("HOST") or ("0.0.0.0" if env_port else "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), partial(Handler, directory=DIST))
    print("docs on http://%s:%d" % (host, port), flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
