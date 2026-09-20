"""The signing half of olanas-listing.py: a local page, the creator wallet, one click.

The launchpad authorises a change with a personal_sign from the creator wallet, and that wallet
lives in a browser extension rather than in a file. So this serves one page on the loopback
interface, hands it the exact message to sign, takes the signature back and sends the PATCH.

The message is built here and never in the page, because the signature covers the object the
launchpad rebuilds, and two implementations of that would be one too many. The page is given a
string and returns a signature over it.

Standard library only, loopback only, and the server stops as soon as it has an answer.
"""

import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8431

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Tenure - update the launchpad listing</title>
<style>
  body { margin: 0; padding: 40px 20px 80px; background: #0A111D; color: #F4F1EA;
         font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  .wrap { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 26px; margin: 0 0 8px; letter-spacing: -.02em; }
  p.lede { color: rgba(244,241,234,.66); margin: 0 0 28px; }
  .panel { background: #121D31; border: 1px solid rgba(244,241,234,.11); border-radius: 14px;
           padding: 20px 22px; margin-bottom: 16px; }
  h2 { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: #F5B84B;
       margin: 0 0 12px; }
  pre { white-space: pre-wrap; word-break: break-word; font: 13px/1.5 ui-monospace, Menlo, Consolas, monospace;
        margin: 0; color: rgba(244,241,234,.86); }
  button { font: 600 15px system-ui, sans-serif; border: 0; border-radius: 12px; padding: 13px 22px;
           background: #F5B84B; color: #15213A; cursor: pointer; }
  button:disabled { opacity: .45; cursor: not-allowed; }
  .msg { border-radius: 12px; padding: 14px 18px; margin-top: 16px; display: none; }
  .msg.show { display: block; }
  .err { background: rgba(255,139,123,.10); border-left: 3px solid #FF8B7B; }
  .ok { background: rgba(123,224,166,.10); border-left: 3px solid #7BE0A6; }
  code { color: #F5B84B; }
</style>
<div class="wrap">
  <h1>Update the launchpad listing</h1>
  <p class="lede">Signed by the creator wallet, sent from this machine. Nothing here asks for a
    key, and the message below is exactly what is signed.</p>

  <div class="panel">
    <h2>Creator wallet</h2>
    <pre id="creator"></pre>
  </div>

  <div class="panel">
    <h2>What changes</h2>
    <pre id="changes"></pre>
  </div>

  <div class="panel">
    <h2>The message</h2>
    <pre id="message"></pre>
  </div>

  <button id="go" type="button">Connect and sign</button>
  <div class="msg" id="out"></div>
</div>
<script>
  var state = null;

  function say(text, kind) {
    var el = document.getElementById("out");
    el.textContent = text;
    el.className = "msg show " + kind;
  }

  async function load() {
    state = await (await fetch("/message")).json();
    document.getElementById("creator").textContent = state.creator;
    document.getElementById("changes").textContent =
      Object.keys(state.changes).map(function (k) { return k + ": " + state.changes[k]; }).join("\\n\\n");
    document.getElementById("message").textContent = state.message;
  }

  document.getElementById("go").addEventListener("click", async function () {
    var go = document.getElementById("go");
    if (!window.ethereum) return say("No wallet was found in this browser.", "err");
    go.disabled = true;
    try {
      var accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      var account = accounts[0];
      if (account.toLowerCase() !== state.creator.toLowerCase()) {
        say("This is " + account + ". The listing can only be changed by " + state.creator + ".", "err");
        go.disabled = false;
        return;
      }
      go.textContent = "waiting for the signature\\u2026";
      var signature = await window.ethereum.request({
        method: "personal_sign", params: [state.message, account]
      });
      go.textContent = "sending\\u2026";
      var res = await fetch("/signed", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ timestamp: state.timestamp, signature: signature })
      });
      var body = await res.json();
      if (!res.ok || body.error) { say(body.error || "The launchpad refused it.", "err"); go.disabled = false; go.textContent = "Connect and sign"; return; }
      say("Updated. The listing now reads: " + body.name, "ok");
      go.textContent = "done";
    } catch (err) {
      // 4001 is the user closing the prompt, which is not a failure worth shouting about.
      if (!err || err.code !== 4001) say(err && err.message ? err.message : String(err), "err");
      go.disabled = false;
      go.textContent = "Connect and sign";
    }
  });

  load();
</script>
"""


def run(creator, changes, build_message, patch):
    """Serves the page until one signature has been taken, then stops.

    @param build_message  (timestamp) -> the exact string to sign
    @param patch          (timestamp, signature) -> the launchpad's answer, or raises
    """
    done = threading.Event()
    result = {}

    class Handler(BaseHTTPRequestHandler):
        timeout = 15

        def log_message(self, *_args):
            pass  # the script says what happened; the access log would only obscure it

        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _local(self):
            # Loopback only, and a Host that is not this machine means somebody else's page.
            host = (self.headers.get("host") or "").split(":")[0]
            return self.client_address[0] in ("127.0.0.1", "::1") and host in ("127.0.0.1", "localhost")

        def do_GET(self):  # noqa: N802
            if not self._local():
                return self.send_error(403)
            if self.path == "/":
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if self.path == "/message":
                # Minted at the moment it is asked for, because it is only valid for five minutes.
                timestamp = str(int(time.time() * 1000))
                return self._json(200, {
                    "creator": creator,
                    "changes": changes,
                    "timestamp": timestamp,
                    "message": build_message(timestamp),
                })
            return self.send_error(404)

        def do_POST(self):  # noqa: N802
            if not self._local() or self.path != "/signed":
                return self.send_error(403)
            length = int(self.headers.get("content-length") or 0)
            if length > 4096:
                return self._json(400, {"error": "too large"})
            try:
                sent = json.loads(self.rfile.read(length).decode())
                answer = patch(sent["timestamp"], sent["signature"])
            except Exception as exc:  # the page shows this to the person who clicked
                return self._json(400, {"error": str(exc)})
            result.update(answer)
            self._json(200, answer)
            done.set()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % PORT
    print("  open %s and sign with %s" % (url, creator))
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        done.wait(timeout=600)
    except KeyboardInterrupt:
        pass
    server.shutdown()
    return result or None
