"""Local preview for the app. Standard library only.

    python dev_server.py [port]        default 8420

Only the page and its assets are servable: this process sits next to source.
"""

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


class Handler(SimpleHTTPRequestHandler):
    timeout = 15  # otherwise a half-sent request pins a thread for as long as the client likes

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        allowed = (
            path in ("/", "/index.html", "/app.js")
            or (path.startswith("/assets/") and ".." not in path)
        )
        return super().do_GET() if allowed else self.send_error(404)

    def end_headers(self):
        self.send_header("cache-control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=HERE))
    print("app on http://127.0.0.1:%d" % port, flush=True)
    httpd.serve_forever()
