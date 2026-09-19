"""CLI.

  python3 -m lpval position <tokenId> [--quote] [--lookback-hours 24]
  python3 -m lpval find [--scan 400] [--min-usdg 50]     find live USDG-paired positions to test with
  python3 -m lpval serve [--host 127.0.0.1] [--port 8402]
"""

import argparse
import json
import sys

from . import abi
from .rpc import Rpc
from .valuation import POSM, RPC_URL, USDG, PositionNotFound, quote, value_position


def _find(rpc: Rpc, scan: int, min_usdg: float, max_found: int = 8, wide: bool = False):
    nxt = abi.words(rpc.eth_calls([(POSM, abi.call_data("nextTokenId()"))])[0])[0]
    ids = list(range(nxt - 1, max(0, nxt - 1 - scan), -1))
    found = []
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        calls = []
        for tid in chunk:
            calls.append((POSM, abi.call_data("getPoolAndPositionInfo(uint256)", abi.enc_uint(tid))))
            calls.append((POSM, abi.call_data("getPositionLiquidity(uint256)", abi.enc_uint(tid))))
        res = rpc.eth_calls(calls)
        for j, tid in enumerate(chunk):
            info, liq = res[2 * j], res[2 * j + 1]
            if not info or not liq or abi.words(liq)[0] == 0:
                continue
            w = abi.words(info)
            if USDG not in (abi.word_to_addr(w[0]), abi.word_to_addr(w[1])):
                continue
            try:
                v = value_position(rpc, tid, lookback_hours=0)
            except Exception:
                continue
            total = (v.get("valueUSDG") or {}).get("total", 0)
            pos = v["position"]
            if wide and not (pos["inRange"] and pos["tickUpper"] - pos["tickLower"] >= 200_000):
                continue
            if total >= min_usdg:
                row = (tid, v["pool"]["token0"]["symbol"], v["pool"]["token1"]["symbol"], total, v["position"]["inRange"])
                found.append(row)
                print(f"{row[0]:>9}  {row[1]}/{row[2]:<10} {row[3]:>14,.2f} USDG  inRange={row[4]}", flush=True)
                if len(found) >= max_found:
                    print(f"stopped after {max_found} matches", flush=True)
                    return
    print(f"scanned {len(ids)} ids, {len(found)} USDG positions >= {min_usdg} USDG")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lpval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("position")
    p.add_argument("token_id", type=int)
    p.add_argument("--quote", action="store_true")
    p.add_argument("--lookback-hours", type=float, default=24.0)
    f = sub.add_parser("find")
    f.add_argument("--scan", type=int, default=400)
    f.add_argument("--min-usdg", type=float, default=50.0)
    f.add_argument("--max", type=int, default=8)
    f.add_argument("--wide", action="store_true", help="only in-range positions with a very wide range")
    n = sub.add_parser("snapshot", help="record fee-growth snapshots for a watchlist (run from cron)")
    n.add_argument("token_ids", type=int, nargs="+")
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8402)
    args = ap.parse_args(argv)

    if args.cmd == "serve":
        from .server import serve

        return serve(args.host, args.port)

    rpc = Rpc(RPC_URL)
    if args.cmd == "find":
        return _find(rpc, args.scan, args.min_usdg, args.max, args.wide)
    if args.cmd == "snapshot":
        for tid in args.token_ids:
            try:
                v = value_position(rpc, tid, lookback_hours=24.0)
                print(f"{tid}: snapshot recorded, value={(v.get('valueUSDG') or {}).get('total')}")
            except Exception as exc:
                print(f"{tid}: {exc}", file=sys.stderr)
        return 0
    try:
        val = value_position(rpc, args.token_id, lookback_hours=args.lookback_hours)
    except PositionNotFound as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.quote:
        val["quote"] = quote(val)
    print(json.dumps(val, indent=2))


if __name__ == "__main__":
    sys.exit(main())
