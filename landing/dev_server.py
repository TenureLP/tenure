"""Local preview: serves the static page and the waitlist endpoint. Standard library only.

    python dev_server.py [port]        default 8410, signups land in waitlist.jsonl next to this file
"""

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("WAITLIST_FILE", os.path.join(HERE, "waitlist.jsonl"))

from api.waitlist import MAX_BODY, process  # noqa: E402
import json  # noqa: E402


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/api/waitlist":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length") or 0)
        status, body = (413, {"message": "Request too large."}) if length > MAX_BODY else process(self.rfile.read(length))
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def end_headers(self):
        self.send_header("cache-control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8410
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=HERE))
    print(f"landing on http://127.0.0.1:{port}")
    httpd.serve_forever()
