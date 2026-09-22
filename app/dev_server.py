"""Local preview for the app. Standard library only.

    python dev_server.py [port]        default 8420

Production is server.py: the same list, plus the headers. Both go through allowed().

Only the page and its assets are servable: this process sits next to source.
"""

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    timeout = 15  # otherwise a half-sent request pins a thread for as long as the client likes

    def allowed(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        # The page and the scripts beside it, nothing else: this process sits next to source, and
        # the source next to it includes a deploy script and a broadcast log.
        return (
            path in ("/", "/index.html")
            or (path.endswith(".js") and "/" not in path[1:])
            or (path.startswith("/assets/") and ".." not in path and "%" not in path)
        )

    def do_GET(self):  # noqa: N802
        return super().do_GET() if self.allowed() else self.send_error(404)

    # HEAD walks the same files as GET, so it answers to the same list, or it would confirm what
    # exists next to the page and how large it is.
    def do_HEAD(self):  # noqa: N802
        return super().do_HEAD() if self.allowed() else self.send_error(404)

    def end_headers(self):
        self.send_header("cache-control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=HERE))
    print("app on http://127.0.0.1:%d" % port, flush=True)
    httpd.serve_forever()
