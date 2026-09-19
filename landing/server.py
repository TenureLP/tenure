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


def storage_is_durable() -> bool:
    """True when a file-backed waitlist survives the container being replaced.

    Locally any path counts. On a platform that throws the filesystem away on every deploy, the
    file has to sit under a mount the operator declared, which we take to be WAITLIST_DATA_DIR.
    Same rule, and the same reason, as the payment ledger in lp-api.
    """
    if not os.environ.get("PORT"):
        return True
    data_dir = os.environ.get("WAITLIST_DATA_DIR")
    path = os.environ.get("WAITLIST_FILE", "")
    return bool(data_dir) and path.startswith(data_dir)


def main():
    env_port = os.environ.get("PORT")
    port = int(env_port) if env_port else 8410
    # Loopback is invisible to the proxy in front of a container, which is the usual reason a first
    # deployment reports itself healthy and answers nothing.
    host = os.environ.get("HOST") or ("0.0.0.0" if env_port else "127.0.0.1")

    # Collecting addresses onto a disk that is about to be discarded is worse than collecting none:
    # the page looks like it works, and the list is silently empty when it is finally read.
    if os.environ.get("WAITLIST_FILE") and not os.environ.get("WAITLIST_WEBHOOK_URL"):
        if not storage_is_durable():
            raise SystemExit(
                "WAITLIST_FILE is set but does not point at a durable path.\n"
                "Every signup would be lost the next time this container is replaced. Attach a\n"
                "volume, set WAITLIST_DATA_DIR to its mount point and put WAITLIST_FILE inside it,\n"
                "or unset WAITLIST_FILE to have signups refused honestly with a 503."
            )

    httpd = ThreadingHTTPServer((host, port), partial(Handler, directory=HERE))
    if os.environ.get("WAITLIST_WEBHOOK_URL"):
        where = "webhook"
    else:
        # Say it plainly at boot rather than letting it be discovered by a visitor who signs up.
        where = os.environ.get("WAITLIST_FILE") or "nowhere, signups answer 503"
    print(f"landing on http://{host}:{port}  signups -> {where}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
