"""Serves the page and the waitlist endpoint. Same handler as the local preview, bound the way a
container needs: every interface, on the port the platform hands us.

    python server.py            local, 127.0.0.1:8410
    PORT=8080 python server.py  container
"""

import os
import sys
from functools import partial
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dev_server import HERE as _HERE, Handler  # noqa: E402,F401


def main():
    env_port = os.environ.get("PORT")
    port = int(env_port) if env_port else 8410
    # Loopback is invisible to the proxy in front of a container, which is the usual reason a first
    # deployment reports itself healthy and answers nothing.
    host = os.environ.get("HOST") or ("0.0.0.0" if env_port else "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), partial(Handler, directory=HERE))
    where = os.environ.get("WAITLIST_WEBHOOK_URL") and "webhook" or os.environ.get("WAITLIST_FILE", "file")
    print(f"landing on http://{host}:{port}  signups -> {where}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
