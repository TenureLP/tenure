"""Live check against the real chain: a payment nobody can prove they made buys nothing.

Takes a real ETH transfer from a recent block, stands the server up as if that transfer's recipient
were the seller, and confirms that presenting the hash alone — the attack the paywall used to be
open to — is refused. Moves no funds and writes to no live endpoint.
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from lpval.rpc import Rpc  # noqa: E402
from lpval.valuation import RPC_URL  # noqa: E402

TOKEN = 2908278
PORT = 8404


def find_transfer(rpc):
    head = rpc.block_number()
    for back in range(0, 3000, 25):
        nums = [hex(head - back - i) for i in range(25)]
        for blk in rpc.batch([("eth_getBlockByNumber", [n, True]) for n in nums]):
            for tx in (blk or {}).get("transactions", []):
                if tx.get("to") and int(tx["value"], 16) > 0 and tx.get("input") in ("0x", ""):
                    return tx
    return None


def get(path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read())


rpc = Rpc(RPC_URL)
tx = find_transfer(rpc)
if not tx:
    sys.exit("no plain ETH transfer found in the last 3000 blocks")
print(f"using tx {tx['hash']}  value={int(tx['value'], 16)} wei  to={tx['to']}")

env = dict(
    os.environ,
    LPVAL_PAY_TO=tx["to"],
    LPVAL_PRICE_WEI=str(int(tx["value"], 16)),
    LPVAL_DB=f"/tmp/lpval_pay_{int(time.time())}.sqlite",
    LPVAL_SNAP_DB="/tmp/lpval_snap.sqlite",
)
srv = subprocess.Popen([sys.executable, "-m", "lpval", "serve", "--port", str(PORT)], cwd=ROOT, env=env,
                       stdout=subprocess.DEVNULL)
time.sleep(1.5)
failures = 0


def check(name, cond, detail=""):
    global failures
    failures += 0 if cond else 1
    print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail else ""))


def proof(**kw):
    return base64.b64encode(json.dumps(dict(scheme="onchain-tx", **kw)).encode()).decode()


try:
    path = f"/v1/position/{TOKEN}"
    s, h, b = get(path)
    extra = (b.get("accepts") or [{}])[0].get("extra", {})
    check("no proof -> 402 x402 v2 with a fresh nonce",
          s == 402 and "PAYMENT-REQUIRED" in h and b.get("x402Version") == 2 and len(extra.get("nonce", "")) == 32)
    check("the challenge advertises that a signature is required", "payer-signature" in extra.get("proof", ""))
    nonce = extra.get("nonce", "0" * 32)

    s, h, b = get(path, {"X402-PAYMENT": proof(txHash=tx["hash"], payer=tx["from"], nonce=nonce, signature="")})
    check("a proof with an empty signature is refused", s == 402, b.get("reason"))

    s, h, b = get(path, {"PAYMENT-SIGNATURE": proof(txHash=tx["hash"], payer=tx["from"], nonce=nonce, signature="0x" + "11" * 65)})
    check("a forged signature is refused", s == 402, b.get("reason"))

    s, h, b = get(path, {"PAYMENT-SIGNATURE": proof(txHash=tx["hash"], payer=tx["from"], nonce="0" * 32, signature="0x" + "11" * 65)})
    check("an invented nonce is refused", s == 402, b.get("reason"))

    s, h, b = get(path, {"PAYMENT-SIGNATURE": "!!!not base64!!!"})
    check("garbage proof is refused, not a crash", s == 402, b.get("reason"))

    s, h, b = get("/health")
    check("health stays free", s == 200)

    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method="OPTIONS")
    with urllib.request.urlopen(req, timeout=10) as r:
        check("CORS preflight allows the payment header",
              r.status == 204 and "payment-signature" in r.headers.get("access-control-allow-headers", ""))
finally:
    srv.terminate()
    srv.wait()

sys.exit(1 if failures else 0)
