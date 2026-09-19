"""Local preview: serves the static page and the waitlist endpoint. Standard library only.

    python dev_server.py [port]        default 8410

Signups land in ../.waitlist/waitlist.jsonl, deliberately outside the directory this server hands
out, and only the page and its assets are servable: this process sits next to source and local state.
"""

import json
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from api.waitlist import process, read_length  # noqa: E402

# Where a local preview keeps signups. It is set when this file is run, never when it is imported:
# server.py imports this module for the handler, and at import time this line was quietly giving the
# deployed service a writable path, which is exactly the misconfiguration the endpoint is supposed
# to refuse.
LOCAL_WAITLIST = os.path.join(HERE, os.pardir, ".waitlist", "waitlist.jsonl")


class Handler(SimpleHTTPRequestHandler):
    timeout = 15  # otherwise a half-sent body pins a thread for as long as the client likes

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/api/waitlist":
            return self.send_error(404)
        length = read_length(self.headers.get("content-length"))
        if length is None:
            status, body = 413, {"message": "Request too large or malformed."}
        else:
            status, body = process(self.rfile.read(length))
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        allowed = path in ("/", "/index.html") or (path.startswith("/assets/") and ".." not in path)
        return super().do_GET() if allowed else self.send_error(404)

    def end_headers(self):
        self.send_header("cache-control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    os.environ.setdefault("WAITLIST_FILE", LOCAL_WAITLIST)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8410
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=HERE))
    print(f"landing on http://127.0.0.1:{port}")
    httpd.serve_forever()
