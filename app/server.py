"""Serves the app in production. Same allowlist as the local preview, bound the way a container
needs, and with the headers a page that asks a wallet to sign things should carry.

    python server.py            local, 127.0.0.1:8420
    PORT=8080 python server.py  container
"""

import os
import re
import sys
from functools import partial
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from dev_server import Handler  # noqa: E402


def origins():
    """Every origin config.js names, read from the file rather than listed twice. A chain added
    there is reachable here without anybody remembering this file exists."""
    with open(os.path.join(HERE, "config.js"), encoding="utf-8") as f:
        text = f.read()
    found = re.findall(r'(?:rpc|api)\s*:\s*"(https://[^"/]+)', text)
    return sorted(set(found))


CSP = "; ".join([
    "default-src 'none'",
    "script-src 'self'",
    # One inline <style> block, and element.style set from script.
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self' " + " ".join(origins()),
    "base-uri 'none'",
    "form-action 'none'",
    # Nothing gets to frame a page that asks for signatures: that is how clicks get stolen.
    "frame-ancestors 'none'",
])


class ProdHandler(Handler):
    def end_headers(self):
        self.send_header("content-security-policy", CSP)
        self.send_header("x-frame-options", "DENY")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("referrer-policy", "no-referrer")
        self.send_header("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("strict-transport-security", "max-age=31536000")
        super().end_headers()

    def log_message(self, fmt, *args):
        # The path and the status, never the client's address.
        sys.stderr.write("%s\n" % (fmt % args))

    def address_string(self):
        return "-"


def main():
    env_port = os.environ.get("PORT")
    port = int(env_port) if env_port else 8420
    host = os.environ.get("HOST") or ("0.0.0.0" if env_port else "127.0.0.1")
    httpd = ThreadingHTTPServer((host, port), partial(ProdHandler, directory=HERE))
    print("app on http://%s:%d" % (host, port), flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
