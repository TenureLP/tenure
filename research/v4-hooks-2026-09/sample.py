"""A uniform random sample of Uniswap v4 positions on Robinhood Chain, and the state each is in.
Public data only; positions are counted, not attributed. Writes sample.jsonl."""
import json
import random
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lp-api"))
from lpval.keccak import keccak256  # noqa: E402

RPC = "https://rpc.mainnet.chain.robinhood.com"
POSM = "0x58daec3116aae6D93017bAAea7749052E8a04fA7"
SV = "0xF3334192D15450CdD385c8B70e03f9A6bD9E673b"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
OUT = sys.argv[2] if len(sys.argv) > 2 else "sample.jsonl"


def call(to, data):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": data}, "latest"]}).encode()
    for attempt in range(6):
        try:
            req = urllib.request.Request(RPC, body, {"content-type": "application/json", "user-agent": "tenure-research/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            if "error" in d:
                return None
            return d["result"]
        except Exception:  # noqa: BLE001
            time.sleep(1.5 + attempt)
    return "ERR"


def s24(v):
    v &= 0xFFFFFF
    return v - (1 << 24) if v >> 23 else v


def one(token_id):
    tid = "%064x" % token_id
    r = call(POSM, "0x7ba03aad" + tid)
    if r == "ERR":
        return {"id": token_id, "err": True}
    if r is None or len(r) < 2 + 64 * 6:
        return {"id": token_id, "gone": True}
    words = [r[2 + 64 * i: 2 + 64 * (i + 1)] for i in range(6)]
    c0, c1 = "0x" + words[0][24:], "0x" + words[1][24:]
    fee, spacing, hooks, info = int(words[2], 16), s24(int(words[3], 16)), "0x" + words[4][24:], int(words[5], 16)
    if int(c0, 16) == 0 and int(c1, 16) == 0 and spacing == 0:
        return {"id": token_id, "gone": True}  # burned: the PositionManager forgets the key
    tl, tu, sub = s24(info >> 8), s24(info >> 32), info & 0xFF
    liq = call(POSM, "0x1efeed33" + tid)
    liq = int(liq, 16) if liq not in (None, "ERR") else None
    pool_id = keccak256(bytes.fromhex("".join(words[:5]))).hex()
    s0 = call(SV, "0xc815641c" + pool_id)
    tick = s24(int(s0[2 + 64: 2 + 128], 16)) if s0 not in (None, "ERR") else None
    return {"id": token_id, "c0": c0, "c1": c1, "fee": fee, "spacing": spacing, "hooks": hooks,
            "tl": tl, "tu": tu, "sub": sub, "liq": liq, "tick": tick, "pool": "0x" + pool_id}


head = int(call(POSM, "0x75794a3c"), 16)
random.seed(46630)
ids = random.sample(range(1, head), N)
t0 = time.time()
with ThreadPoolExecutor(max_workers=6) as pool, open(OUT, "w") as out:
    for i, rec in enumerate(pool.map(one, ids)):
        out.write(json.dumps(rec) + "\n")
        if (i + 1) % 200 == 0:
            print("%d/%d sampled, %ds" % (i + 1, N, time.time() - t0), flush=True)
print("DONE", N, "of", head - 1, "positions", flush=True)
