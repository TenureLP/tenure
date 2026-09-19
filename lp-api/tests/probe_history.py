"""Manual probe: how far back does the public RPC serve eth_call state?"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lpval import abi  # noqa: E402
from lpval.rpc import Rpc  # noqa: E402
from lpval.valuation import POSM, RPC_URL  # noqa: E402

rpc = Rpc(RPC_URL)
head = rpc.block_number()
data = abi.call_data("nextTokenId()")
for label, back in [("10s", 100), ("1min", 600), ("10min", 6000), ("1h", 36000), ("6h", 216000), ("24h", 864000)]:
    r = rpc.eth_calls([(POSM, data)], head - back)[0]
    print(f"{label:>6} (-{back} blocks):", "ok" if r else "unavailable")
