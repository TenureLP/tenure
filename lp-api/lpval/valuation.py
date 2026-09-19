"""Read a Uniswap v4 position from chain and value it."""

import os
import time

from . import abi, snapshots, v4math
from .keccak import keccak256
from .rpc import REVERTED, Rpc, UpstreamError

CHAIN_ID = 4663
RPC_URL = os.environ.get("LPVAL_RPC", "https://rpc.mainnet.chain.robinhood.com")
POSM = "0x58daec3116aae6d93017baaea7749052e8a04fa7"
STATE_VIEW = "0xf3334192d15450cdd385c8b70e03f9a6bd9e673b"
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
NATIVE = "0x" + "00" * 20
SHORT_WINDOW_BLOCKS = 5_000  # about 8 minutes of 100 ms blocks, within what the public RPC serves
BLOCK_SECONDS = 0.1  # only used to aim at a block; the window is measured from its own timestamp

_token_cache = {NATIVE: {"address": NATIVE, "symbol": "ETH", "decimals": 18}}


class PositionNotFound(Exception):
    pass


def _fmt(raw: int, decimals: int) -> str:
    s = str(raw).rjust(decimals + 1, "0")
    whole, frac = (s[:-decimals], s[-decimals:]) if decimals else (s, "")
    frac = frac.rstrip("0")
    return f"{whole}.{frac}" if frac else whole


def _load_tokens(rpc: Rpc, addrs):
    missing = [a for a in addrs if a not in _token_cache]
    if missing:
        calls = []
        for a in missing:
            calls.append((a, abi.call_data("decimals()")))
            calls.append((a, abi.call_data("symbol()")))
        res = rpc.eth_calls(calls)
        for i, a in enumerate(missing):
            dec_raw, sym_raw = res[2 * i], res[2 * i + 1]
            ok_dec = isinstance(dec_raw, bytes) and len(dec_raw) >= 32
            ok_sym = isinstance(sym_raw, bytes) and len(sym_raw) > 0
            decimals = abi.words(dec_raw)[0] if ok_dec else 18
            symbol = abi.decode_string(sym_raw) if ok_sym else "?"
            _token_cache[a] = {"address": a, "symbol": symbol, "decimals": int(decimals)}
    return [_token_cache[a] for a in addrs]


def read_position(rpc: Rpc, token_id: int, block="latest") -> dict:
    """Raw on-chain facts about a position, no pricing."""
    tid = abi.enc_uint(token_id)
    r = rpc.eth_calls(
        [
            (POSM, abi.call_data("getPoolAndPositionInfo(uint256)", tid)),
            (POSM, abi.call_data("getPositionLiquidity(uint256)", tid)),
            (POSM, abi.call_data("ownerOf(uint256)", tid)),
        ],
        block,
    )
    if r[0] is REVERTED or r[1] is REVERTED:
        raise PositionNotFound(f"token {token_id} not found")
    if not r[0] or len(r[0]) < 192:
        raise PositionNotFound(f"token {token_id} not found")
    w = abi.words(r[0])
    if w[0] == 0 and w[1] == 0 and w[5] == 0:
        raise PositionNotFound(f"token {token_id} not found")

    info = w[5]
    tick_lower = abi.to_signed((info >> 8) & 0xFFFFFF, 24)
    tick_upper = abi.to_signed((info >> 32) & 0xFFFFFF, 24)
    pool_id = keccak256(r[0][:160])
    c0, c1 = abi.word_to_addr(w[0]), abi.word_to_addr(w[1])

    r2 = rpc.eth_calls(
        [
            (STATE_VIEW, abi.call_data("getSlot0(bytes32)", pool_id)),
            (
                STATE_VIEW,
                abi.call_data(
                    "getFeeGrowthInside(bytes32,int24,int24)", pool_id, abi.enc_int(tick_lower), abi.enc_int(tick_upper)
                ),
            ),
            (
                STATE_VIEW,
                abi.call_data(
                    "getPositionInfo(bytes32,address,int24,int24,bytes32)",
                    pool_id,
                    abi.enc_addr(POSM),
                    abi.enc_int(tick_lower),
                    abi.enc_int(tick_upper),
                    tid,
                ),
            ),
        ],
        block,
    )
    if any(x is REVERTED for x in r2):
        raise PositionNotFound(f"pool state unavailable for token {token_id}")
    if not all(r2):
        raise UpstreamError(f"the chain did not answer for token {token_id}")
    slot0, fg, pinfo = abi.words(r2[0]), abi.words(r2[1]), abi.words(r2[2])
    t0, t1 = _load_tokens(rpc, [c0, c1])

    return {
        "tokenId": token_id,
        "owner": abi.word_to_addr(abi.words(r[2])[0]) if isinstance(r[2], bytes) and r[2] else None,
        "poolId": "0x" + pool_id.hex(),
        "token0": t0,
        "token1": t1,
        "feePips": w[2],
        "tickSpacing": abi.to_signed(w[3], 24),
        "hooks": abi.word_to_addr(w[4]),
        "hasSubscriber": bool(info & 0xFF),
        "tickLower": tick_lower,
        "tickUpper": tick_upper,
        "liquidity": abi.words(r[1])[0] if r[1] else 0,
        "sqrtPriceX96": slot0[0],
        "tick": abi.to_signed(slot0[1], 24),
        "lpFeePips": slot0[3],
        "feeGrowthInside0": fg[0],
        "feeGrowthInside1": fg[1],
        "feeGrowthInside0Last": pinfo[1],
        "feeGrowthInside1Last": pinfo[2],
    }


def _usdg_value(p: dict, amount0: int, amount1: int):
    """Value a pair of raw amounts in USDG using the pool's own price. None if USDG is not in the pair."""
    d0, d1 = p["token0"]["decimals"], p["token1"]["decimals"]
    price01 = v4math.price_token0_in_token1(p["sqrtPriceX96"], d0, d1)
    a0, a1 = amount0 / 10 ** d0, amount1 / 10 ** d1
    if p["token1"]["address"] == USDG:
        return a0 * price01 + a1
    if p["token0"]["address"] == USDG:
        return a0 + (a1 / price01 if price01 else 0.0)
    return None


def value_position(rpc: Rpc, token_id: int, block="latest", lookback_hours: float = 24.0) -> dict:
    p = read_position(rpc, token_id, block)
    d0, d1 = p["token0"]["decimals"], p["token1"]["decimals"]
    sqrt_a = v4math.sqrt_ratio_at_tick(p["tickLower"])
    sqrt_b = v4math.sqrt_ratio_at_tick(p["tickUpper"])
    amt0, amt1 = v4math.amounts_for_liquidity(p["sqrtPriceX96"], sqrt_a, sqrt_b, p["liquidity"])
    fee0 = v4math.fees_owed(p["feeGrowthInside0"], p["feeGrowthInside0Last"], p["liquidity"])
    fee1 = v4math.fees_owed(p["feeGrowthInside1"], p["feeGrowthInside1Last"], p["liquidity"])

    principal_usdg = _usdg_value(p, amt0, amt1)
    fees_usdg = _usdg_value(p, fee0, fee1)

    out = {
        "tokenId": token_id,
        "chainId": CHAIN_ID,
        "owner": p["owner"],
        "pool": {
            "poolId": p["poolId"],
            "token0": p["token0"],
            "token1": p["token1"],
            "keyFeePips": p["feePips"],  # 8388608 (0x800000) means a dynamic fee set by the hook
            "currentLpFeePips": p["lpFeePips"],
            "tickSpacing": p["tickSpacing"],
            "hooks": p["hooks"],
        },
        "position": {
            "tickLower": p["tickLower"],
            "tickUpper": p["tickUpper"],
            "liquidity": str(p["liquidity"]),
            "inRange": p["tickLower"] <= p["tick"] < p["tickUpper"],
            "hasSubscriber": p["hasSubscriber"],
            "priceLower": v4math.price_token0_in_token1(sqrt_a, d0, d1),
            "priceUpper": v4math.price_token0_in_token1(sqrt_b, d0, d1),
        },
        "price": {
            "token0InToken1": v4math.price_token0_in_token1(p["sqrtPriceX96"], d0, d1),
            "tick": p["tick"],
            "sqrtPriceX96": str(p["sqrtPriceX96"]),
        },
        "principal": {"amount0": _fmt(amt0, d0), "amount1": _fmt(amt1, d1), "raw0": str(amt0), "raw1": str(amt1)},
        "uncollectedFees": {"amount0": _fmt(fee0, d0), "amount1": _fmt(fee1, d1), "raw0": str(fee0), "raw1": str(fee1)},
        "valueUSDG": (
            {"principal": round(principal_usdg, 6), "fees": round(fees_usdg, 6), "total": round(principal_usdg + fees_usdg, 6)}
            if principal_usdg is not None
            else None
        ),
        "valueNote": None if principal_usdg is not None else "USDG is not one of the pair's tokens; no USDG quote in v0.1",
    }
    out["feeRate"] = _fee_rate(rpc, p, principal_usdg, lookback_hours) if lookback_hours else None
    return out


def _rpc_window(rpc: Rpc, p: dict, lookback_hours: float):
    """Reads `feeGrowthInside` as it stood one lookback ago, at whatever depth the node serves.

    An archive node answers the whole window, which is what makes a fee rate worth quoting on the
    very first request instead of after a day of collecting our own snapshots. A pruned node
    answers nothing that old, so we retry once over the short window the public node does serve,
    and say which of the two the number came from.

    Returns (source, elapsed_seconds, (feeGrowth0, feeGrowth1)) or None.
    """
    now_block = rpc.block_number()
    pool_id = bytes.fromhex(p["poolId"][2:])
    data = abi.call_data(
        "getFeeGrowthInside(bytes32,int24,int24)",
        pool_id,
        abi.enc_int(p["tickLower"]),
        abi.enc_int(p["tickUpper"]),
    )

    wanted = int(lookback_hours * 3600 / BLOCK_SECONDS)
    attempts = [(wanted, "rpc-archive")]
    # Only ever fall back to a *shorter* window. Quietly returning more history than was asked for
    # would answer a different question than the caller's, and they price on the answer.
    if SHORT_WINDOW_BLOCKS < wanted:
        attempts.append((SHORT_WINDOW_BLOCKS, "rpc-short-window"))

    now_ts = None
    for blocks_back, source in attempts:
        if blocks_back <= 0 or blocks_back >= now_block:
            continue
        past_block = now_block - blocks_back
        try:
            # persist: "I cannot serve that state" is a fact about one node, not about the chain.
            # A provider fronting a pool answers it from some of its nodes and not others, so
            # taking the first refusal at face value hands the same position a 24 hour rate or an
            # eight minute one depending on the draw, and a rent is quoted off the difference.
            past = rpc.eth_calls([(STATE_VIEW, data)], past_block, persist=True)[0]
        except Exception:
            continue  # nobody serves it that far back; try the shorter window
        if not isinstance(past, bytes) or len(past) < 64:
            continue
        if now_ts is None:
            now_ts = rpc.block_timestamp(now_block)
        elapsed = now_ts - rpc.block_timestamp(past_block)
        if elapsed > 0:
            return source, elapsed, abi.words(past)
    return None


def _fee_rate(rpc: Rpc, p: dict, principal_usdg, lookback_hours: float) -> dict:
    """Fees this position's range earned per unit of liquidity over a lookback window."""
    try:
        now = int(time.time())
        snap = snapshots.oldest_within(p["poolId"], p["tickLower"], p["tickUpper"], lookback_hours * 3600, now)
        snapshots.record(p["poolId"], p["tickLower"], p["tickUpper"], p["feeGrowthInside0"], p["feeGrowthInside1"], now)
        if snap:
            source, elapsed, pw = "snapshot", now - snap[0], (snap[1], snap[2])
        else:
            window = _rpc_window(rpc, p, lookback_hours)
            if window is None:
                return {"available": False, "reason": "no snapshot yet and historical state not served by this RPC"}
            source, elapsed, pw = window
        if elapsed <= 0:
            return {"available": False, "reason": "could not measure elapsed time"}
        f0 = v4math.fees_owed(p["feeGrowthInside0"], pw[0], p["liquidity"])
        f1 = v4math.fees_owed(p["feeGrowthInside1"], pw[1], p["liquidity"])
        fees_usdg = _usdg_value(p, f0, f1)
        res = {
            "available": True,
            "source": source,
            # An archive node answering the full window is as good a measurement as our own
            # snapshot, and reads exact state rather than what we happened to record. Only a
            # window that is short, or one we had to shrink to get an answer, is weak evidence.
            "lowConfidence": elapsed < 3600 or source == "rpc-short-window",
            "windowSeconds": elapsed,
            "fees0": _fmt(f0, p["token0"]["decimals"]),
            "fees1": _fmt(f1, p["token1"]["decimals"]),
            "feesUSDG": round(fees_usdg, 6) if fees_usdg is not None else None,
            "note": "Assumes current liquidity held over the whole window. Unreliable if the range ticks were "
            "uninitialized at the start of the window.",
        }
        if fees_usdg is not None and principal_usdg:
            per_second = fees_usdg / elapsed
            res["feesPerDayUSDG"] = round(per_second * 86400, 6)
            res["feeAprPercent"] = round(per_second * 86400 * 365 / principal_usdg * 100, 4)
            res["plausible"] = fees_usdg < principal_usdg  # wrap-around garbage shows up as absurd fees
        return res
    except Exception as exc:  # keep valuation usable even if the history probe fails
        return {"available": False, "reason": str(exc)}


def quote(valuation: dict, term_days: int = 7, haircut: float = 0.20, rent_share: float = 0.5) -> dict:
    """Indicative sale-and-leaseback terms. A starting point for negotiation, not advice."""
    v = valuation.get("valueUSDG")
    if not v:
        return {"available": False, "reason": valuation.get("valueNote") or "no USDG value"}
    if not v["total"]:
        # A closed or never-funded position still reads as in range over its full tick span, so
        # eligibility alone would call it fundable. There is nothing to sell.
        return {"available": False, "reason": "the position holds no liquidity"}

    fr = valuation.get("feeRate") or {}
    if not (fr.get("available") and fr.get("plausible") and fr.get("feesPerDayUSDG") is not None):
        # The vault rejects a listing whose rent is zero, so a price without a rent is not a set of
        # terms anybody could act on. Say so instead of returning half of a quote as available.
        return {
            "available": False,
            "reason": fr.get("reason") or "the fee rate is not usable, so no rent can be derived from it",
            "marketValueUSDG": v["total"],
        }

    price = v["total"] * (1 - haircut)
    rent = fr["feesPerDayUSDG"] * term_days * rent_share
    return {
        "available": True,
        "termDays": term_days,
        "inputs": {"haircut": haircut, "rentShareOfExpectedFees": rent_share},
        "marketValueUSDG": v["total"],
        "suggestedSalePriceUSDG": round(price, 2),
        "suggestedBuybackPriceUSDG": round(price, 2),
        "expectedFeesOverTermUSDG": round(fr["feesPerDayUSDG"] * term_days, 4),
        "suggestedRentUSDG": round(rent, 4),
        # The rent is only as good as the window it was measured over. A caller pricing a deal
        # should know whether that was a day of history or eight minutes of it.
        "feeRateLowConfidence": bool(fr.get("lowConfidence")),
        "eligibility": {
            "inRange": valuation["position"]["inRange"],
            "noSubscriber": not valuation["position"]["hasSubscriber"],
        },
        "disclaimer": "Indicative model output. Not a guarantee of funding or of resale value.",
    }
