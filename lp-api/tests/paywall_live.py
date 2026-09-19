"""Live paywall test that moves no funds.

Finds a real, recent ETH transfer on Robinhood Chain, starts the server configured as if that
transfer's recipient were the seller, and presents the hash as an Olanas-style proof.
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


def proof(tx_hash, payer):
    return base64.b64encode(json.dumps({"scheme": "onchain-tx", "txHash": tx_hash, "payer": payer}).encode()).decode()


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
srv = subprocess.Popen(
    [sys.executable, "-m", "lpval", "serve", "--port", str(PORT)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL
)
time.sleep(1.5)
failures = 0


def check(name, cond, detail=""):
    global failures
    failures += 0 if cond else 1
    print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail else ""))


try:
    path = f"/v1/position/{TOKEN}"
    s, h, b = get(path)
    check("no proof -> 402 with PAYMENT-REQUIRED header", s == 402 and "PAYMENT-REQUIRED" in h, b.get("payTo"))

    s, h, b = get(path, {"PAYMENT-SIGNATURE": proof(tx["hash"], "0x" + "11" * 20)})
    check("wrong payer -> 402", s == 402, b.get("reason"))

    s, h, b = get(path, {"PAYMENT-SIGNATURE": "not-base64-json"})
    check("garbage proof -> 402", s == 402, b.get("reason"))

    s, h, b = get(path, {"PAYMENT-SIGNATURE": proof(tx["hash"], tx["from"])})
    ok = s == 200 and "PAYMENT-RESPONSE" in h and b.get("tokenId") == TOKEN
    check("valid proof -> 200 with PAYMENT-RESPONSE receipt", ok)
    if ok:
        print("     receipt:", json.loads(base64.b64decode(h["PAYMENT-RESPONSE"])))

    s, h, b = get(path, {"PAYMENT-SIGNATURE": proof(tx["hash"], tx["from"])})
    check("replay of the same proof -> 402", s == 402, b.get("reason"))

    s, h, b = get(path, {"X-Payment-Tx": tx["hash"]})
    check("replay via X-Payment-Tx -> 402", s == 402, b.get("reason"))
finally:
    srv.terminate()
    srv.wait()

sys.exit(1 if failures else 0)
