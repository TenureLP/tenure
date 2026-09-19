"""Waitlist endpoint. Runs as a Vercel Python function and is reused by dev_server.py.

Where signups go, in order:
  1. WAITLIST_WEBHOOK_URL set: each signup is POSTed there as JSON. A Discord webhook URL is detected
     and gets a Discord-shaped message. Any other URL (Google Apps Script, Make, Zapier, your own API)
     receives {"email", "role", "source", "ts"}.
  2. Otherwise, off Vercel: appended to WAITLIST_FILE (default waitlist.jsonl), with de-duplication.
  3. Otherwise: 503, so a misconfigured deployment fails loudly instead of dropping signups.
"""

import json
import os
import re
import time
import urllib.request
from http.server import BaseHTTPRequestHandler

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
ROLES = {"lp", "financier", "both"}
SOURCES = {"hero", "footer"}
MAX_BODY = 4096


def _deliver_webhook(url: str, record: dict):
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        payload = {
            "content": f"Waitlist: `{record['email']}` · {record['role']} · {record['source']}",
            "allowed_mentions": {"parse": []},
        }
    else:
        payload = record
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "user-agent": "tenure-waitlist/1"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"webhook answered {resp.status}")


def _deliver_file(path: str, record: dict) -> bool:
    """Returns True when the email was already present."""
    seen = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen.add(json.loads(line)["email"])
                except Exception:
                    continue
    if record["email"] in seen:
        return True
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return False


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
    role = data.get("role") if data.get("role") in ROLES else "lp"
    source = data.get("source") if data.get("source") in SOURCES else "unknown"
    record = {"email": email, "role": role, "source": source, "ts": int(time.time())}

    url = os.environ.get("WAITLIST_WEBHOOK_URL", "").strip()
    try:
        if url:
            _deliver_webhook(url, record)
            return 200, {"ok": True}
        if not os.environ.get("VERCEL"):
            dup = _deliver_file(os.environ.get("WAITLIST_FILE", "waitlist.jsonl"), record)
            return 200, {"ok": True, "duplicate": dup}
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
        length = int(self.headers.get("content-length") or 0)
        if length > MAX_BODY:
            return self._send(413, {"message": "Request too large."})
        status, body = process(self.rfile.read(length))
        self._send(status, body)

    def do_GET(self):  # noqa: N802
        self._send(405, {"message": "POST only."})
