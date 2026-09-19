"""Manual probe: does the RPC accept JSON-RPC batches, and how fast is it?"""
import json
import time
import urllib.request

URL = "https://rpc.mainnet.chain.robinhood.com"


def post(payload):
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode(), headers={"content-type": "application/json", "user-agent": "lpval/0.1"}
    )
    t = time.time()
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read()
    return time.time() - t, body[:300]


print("single:", post({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}))
batch = [{"jsonrpc": "2.0", "id": i, "method": "eth_blockNumber", "params": []} for i in range(1, 6)]
try:
    print("batch5:", post(batch))
except Exception as e:
    print("batch5 failed:", repr(e))
big = [{"jsonrpc": "2.0", "id": i, "method": "eth_blockNumber", "params": []} for i in range(1, 101)]
try:
    dt, body = post(big)
    print("batch100:", dt, body[:120])
except Exception as e:
    print("batch100 failed:", repr(e))
