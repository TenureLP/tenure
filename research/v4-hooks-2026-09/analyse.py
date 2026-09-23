"""Totals over the pool census and the position sample. Public data, aggregated."""
import json
import sys
from collections import Counter

import os
D = os.path.dirname(os.path.abspath(__file__)) + os.sep
FLAGS = [  # bit -> name, v4 Hooks.sol
    (13, "beforeInitialize"), (12, "afterInitialize"), (11, "beforeAddLiquidity"), (10, "afterAddLiquidity"),
    (9, "beforeRemoveLiquidity"), (8, "afterRemoveLiquidity"), (7, "beforeSwap"), (6, "afterSwap"),
    (5, "beforeDonate"), (4, "afterDonate"), (3, "beforeSwapReturnDelta"), (2, "afterSwapReturnDelta"),
    (1, "afterAddLiquidityReturnDelta"), (0, "afterRemoveLiquidityReturnDelta"),
]
DYNAMIC = 0x800000


def perms(hook):
    bits = int(hook, 16) & 0x3FFF
    return {name for bit, name in FLAGS if bits >> bit & 1}


listed = {}
for h in json.load(open(D + "hooklist.json")):
    if h["hook"].get("chain") == "robinhood":
        listed[h["hook"]["address"].lower()] = h

pools = [json.loads(l) for l in open(D + "pools.jsonl")]
zero = "0x" + "0" * 40
out = {"pools": len(pools)}
hooked = [p for p in pools if p["hooks"] != zero]
out["hooked"] = len(hooked)
out["dynamicFee"] = sum(1 for p in pools if p["fee"] == DYNAMIC)
by_hook = Counter(p["hooks"] for p in hooked)
out["distinctHooks"] = len(by_hook)
out["hooksListed"] = sum(1 for h in by_hook if h in listed)
out["poolsOnListedHooks"] = sum(n for h, n in by_hook.items() if h in listed)

cat = Counter()
for p in hooked:
    ps = perms(p["hooks"])
    if "afterRemoveLiquidityReturnDelta" in ps:
        cat["can take from withdrawals"] += 1
    if ps & {"beforeRemoveLiquidity", "afterRemoveLiquidity"}:
        cat["runs on every withdrawal"] += 1
    if ps & {"beforeSwapReturnDelta", "afterSwapReturnDelta"}:
        cat["can change what a swap pays"] += 1
    if ps & {"beforeAddLiquidity", "afterAddLiquidity"}:
        cat["runs on every deposit"] += 1
    if not ps & {"beforeAddLiquidity", "afterAddLiquidity", "beforeRemoveLiquidity", "afterRemoveLiquidity",
                 "beforeSwap", "afterSwap", "beforeSwapReturnDelta", "afterSwapReturnDelta"}:
        cat["only watches initialisation"] += 1
out["hookedPoolCapabilities"] = cat

top = []
for h, n in by_hook.most_common(15):
    meta = listed.get(h)
    top.append({
        "hook": h, "pools": n, "name": meta["hook"]["name"] if meta else None,
        "upgradeable": meta["properties"].get("upgradeable") if meta else None,
        "audited": bool(meta["hook"].get("auditUrl")) if meta else None,
        "swapAccess": meta["properties"].get("swapAccess") if meta else None,
        "perms": sorted(perms(h)),
    })
out["topHooks"] = top
out["top10Share"] = round(sum(n for _, n in by_hook.most_common(10)) / max(1, len(hooked)) * 100, 1)

# first block and pace
blocks = sorted(p["block"] for p in pools)
out["firstBlock"], out["lastBlock"] = blocks[0], blocks[-1]

try:
    sample = [json.loads(l) for l in open(D + "sample.jsonl")]
except FileNotFoundError:
    sample = []
s = Counter()
widths = []
for r in sample:
    if r.get("err"):
        s["unreadable"] += 1
        continue
    if r.get("gone"):
        s["burned"] += 1
        continue
    s["exist"] += 1
    if r["hooks"] != zero:
        s["in a hooked pool"] += 1
    if r.get("liq") == 0:
        s["empty"] += 1
        continue
    s["live"] += 1
    if r["tick"] is None:
        continue
    inside = r["tl"] <= r["tick"] < r["tu"]
    s["live in range" if inside else "live out of range"] += 1
    if r["tl"] <= -886000 or r["tu"] >= 886000:
        s["live one-sided to the edge (launch shape)"] += 1
    else:
        widths.append((1.0001 ** (r["tu"] - r["tl"]) - 1) * 100)
    if r["sub"]:
        s["live with a subscriber"] += 1
out["sample"] = s
if widths:
    widths.sort()
    out["sampleBoundedWidthPct"] = {"p10": round(widths[len(widths) // 10], 1), "median": round(widths[len(widths) // 2], 1),
                                    "p90": round(widths[len(widths) * 9 // 10], 1), "n": len(widths)}
print(json.dumps(out, indent=1))
