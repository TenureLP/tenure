"""Every Uniswap v4 pool ever initialised on Robinhood Chain, from the PoolManager's Initialize
events. Public data only. Writes one JSON line per pool to pools.jsonl and prints progress.

Windows split in half whenever the node says a window holds more than its 10,000-log limit."""
import json
import sys
import time
import urllib.request

RPC = "https://rpc.mainnet.chain.robinhood.com"
PM = "0x8366a39CC670B4001A1121B8F6A443A643e40951"
TOPIC = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"
OUT = sys.argv[1] if len(sys.argv) > 1 else "pools.jsonl"


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for attempt in range(8):
        try:
            req = urllib.request.Request(RPC, body, {"content-type": "application/json", "user-agent": "tenure-research/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            if "error" in d:
                return None, d["error"].get("message", "")
            return d["result"], None
        except Exception as e:  # noqa: BLE001
            time.sleep(2 + attempt * 2)
            last = str(e)
    return None, "transport: " + last


def word(data, i):
    return data[2 + 64 * i: 2 + 64 * (i + 1)]


def signed(h, bits):
    v = int(h, 16)
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


head = int(rpc("eth_blockNumber", [])[0], 16)
stack = [(0, head)]
n = 0
t0 = time.time()
with open(OUT, "w") as out:
    while stack:
        lo, hi = stack.pop()
        logs, err = rpc("eth_getLogs", [{"address": PM, "fromBlock": hex(lo), "toBlock": hex(hi), "topics": [TOPIC]}])
        if err is not None:
            if "exceeds limit" in err or "too many" in err.lower() or "range" in err.lower():
                mid = (lo + hi) // 2
                stack.append((mid + 1, hi))
                stack.append((lo, mid))
                continue
            print("ERROR", lo, hi, err, flush=True)
            time.sleep(5)
            stack.append((lo, hi))
            continue
        for l in logs:
            d = l["data"]
            out.write(json.dumps({
                "id": l["topics"][1],
                "c0": "0x" + l["topics"][2][26:],
                "c1": "0x" + l["topics"][3][26:],
                "fee": int(word(d, 0), 16),
                "spacing": signed(word(d, 1), 24),
                "hooks": "0x" + word(d, 2)[24:],
                "tick": signed(word(d, 4), 24),
                "block": int(l["blockNumber"], 16),
            }) + "\n")
        n += len(logs)
        print("%d pools, blocks %d-%d done, %ds" % (n, lo, hi, time.time() - t0), flush=True)
print("DONE", n, "pools to block", head, flush=True)
