"""Local preview for the landing. Standard library only.

    python dev_server.py [port]        default 8410

Two pages and their assets, nothing else: this process sits next to source. Production is
server.py, which uses the same handler.
"""

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

# Clean url -> file. Every page the landing has is listed here, so adding one is a deliberate act.
PAGES = {"/": "/index.html", "/index.html": "/index.html", "/olanas": "/olanas.html", "/olanas.html": "/olanas.html"}


class Handler(SimpleHTTPRequestHandler):
    timeout = 15  # otherwise a half-sent request pins a thread for as long as the client likes

    def resolve(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path in PAGES:
            return PAGES[path]
        if path.startswith("/assets/") and ".." not in path and "%" not in path:
            return path
        return None

    def do_GET(self):  # noqa: N802
        target = self.resolve()
        if target is None:
            return self.send_error(404)
        self.path = target
        return super().do_GET()

    # HEAD answers to the same list as GET, or it would confirm what else sits in this folder.
    def do_HEAD(self):  # noqa: N802
        target = self.resolve()
        if target is None:
            return self.send_error(404)
        self.path = target
        return super().do_HEAD()

    def end_headers(self):
        self.send_header("cache-control", "no-cache")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8410
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=HERE))
    print(f"landing on http://127.0.0.1:{port}")
    httpd.serve_forever()
