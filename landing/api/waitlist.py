"""Waitlist endpoint. Runs as a Vercel Python function and is reused by dev_server.py.

Where signups go, in order:
  1. WAITLIST_WEBHOOK_URL set: each signup is POSTed there as JSON. A Discord webhook URL is detected
     and gets a Discord-shaped message. Any other URL (Google Apps Script, Make, Zapier, your own API)
     receives {"email", "role", "source", "ts"}.
  2. Otherwise, off Vercel: appended to WAITLIST_FILE. Duplicates are removed when the list is read,
     not on the way in: re-reading the whole file per signup is linear in its size, and the
     check-then-append it would need is a race between concurrent requests anyway.
  3. Otherwise: 503, so a misconfigured deployment fails loudly instead of dropping signups.
"""

import json
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
ROLES = {"lp", "financier", "both"}
SOURCES = {"hero", "footer"}
MAX_BODY = 4096
UNSAFE_IN_CHAT = re.compile(r"[`\\\[\]()<>*_~|]")
_file_lock = threading.Lock()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _safe(text: str) -> str:
    """The email ends up in a chat message the team reads. Left raw, a signup could close a code
    span and render as a link: a phishing message wearing our own alert bot's face."""
    return UNSAFE_IN_CHAT.sub("", text)


def _deliver_webhook(url: str, record: dict):
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        payload = {
            "content": "Waitlist: {} · {} · {}".format(
                _safe(record["email"]), _safe(record["role"]), _safe(record["source"])
            ),
            "allowed_mentions": {"parse": []},
        }
    else:
        payload = record
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "user-agent": "tenure-waitlist/1"},
    )
    # No redirects: a hijacked or fat-fingered webhook must not be able to bounce signups elsewhere,
    # least of all to an address inside our own network.
    with urllib.request.build_opener(_NoRedirect).open(req, timeout=8) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"webhook answered {resp.status}")


def _deliver_file(path: str, record: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _file_lock, open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def read_length(header):
    """None means refuse. A negative Content-Length would make rfile.read() drain the socket until
    the client closes it, turning one request into unbounded memory."""
    try:
        length = int(header or 0)
    except (TypeError, ValueError):
        return None
    return length if 0 <= length <= MAX_BODY else None


def process(raw: bytes):
    """Pure request logic. Returns (status, body_dict)."""
    try:
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict):
            raise ValueError
    except Exception:
        return 400, {"message": "Malformed request."}

    if str(data.get("company") or "").strip():  # honeypot: bots fill it, people never see it
        return 200, {"ok": True}

    email = str(data.get("email") or "").strip().lower()
    if len(email) > 254 or not EMAIL.match(email):
        return 400, {"message": "That email does not look right."}
    # A list or a dict here would raise "unhashable type" on the membership test, so check the type
    # before trusting the value at all.
    raw_role, raw_source = data.get("role"), data.get("source")
    role = raw_role if isinstance(raw_role, str) and raw_role in ROLES else "lp"
    source = raw_source if isinstance(raw_source, str) and raw_source in SOURCES else "unknown"
    record = {"email": email, "role": role, "source": source, "ts": int(time.time())}

    url = os.environ.get("WAITLIST_WEBHOOK_URL", "").strip()
    try:
        if url:
            _deliver_webhook(url, record)
            return 200, {"ok": True}
        if not os.environ.get("VERCEL"):
            _deliver_file(os.environ.get("WAITLIST_FILE", "waitlist.jsonl"), record)
            # Deliberately the same answer whether or not this address was already on the list.
            # Anything else lets a stranger ask the endpoint who signed up.
            return 200, {"ok": True}
    except Exception:
        return 502, {"message": "We could not save that. Please try again in a moment."}
    return 503, {"message": "The waitlist is not configured yet."}


class handler(BaseHTTPRequestHandler):  # noqa: N801  (name required by Vercel)
    def _send(self, status: int, body: dict):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        length = read_length(self.headers.get("content-length"))
        if length is None:
            return self._send(413, {"message": "Request too large or malformed."})
        status, body = process(self.rfile.read(length))
        self._send(status, body)

    def do_GET(self):  # noqa: N802
        self._send(405, {"message": "POST only."})
