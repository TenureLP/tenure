"""Read a Uniswap v4 position from chain and value it."""

import os
import time

from . import abi, snapshots, v4math
from .keccak import keccak256
from .rpc import Rpc

CHAIN_ID = 4663
RPC_URL = os.environ.get("LPVAL_RPC", "https://rpc.mainnet.chain.robinhood.com")
POSM = "0x58daec3116aae6d93017baaea7749052e8a04fa7"
STATE_VIEW = "0xf3334192d15450cdd385c8b70e03f9a6bd9e673b"
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
NATIVE = "0x" + "00" * 20
SHORT_WINDOW_BLOCKS = 5_000  # about 8 minutes of 100 ms blocks, within what the public RPC serves

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
            decimals = abi.words(dec_raw)[0] if dec_raw else 18
            symbol = abi.decode_string(sym_raw) if sym_raw else "?"
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
    if not all(r2):
        raise PositionNotFound(f"pool state unavailable for token {token_id}")
    slot0, fg, pinfo = abi.words(r2[0]), abi.words(r2[1]), abi.words(r2[2])
    t0, t1 = _load_tokens(rpc, [c0, c1])

    return {
        "tokenId": token_id,
        "owner": abi.word_to_addr(abi.words(r[2])[0]) if r[2] else None,
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


def _fee_rate(rpc: Rpc, p: dict, principal_usdg, lookback_hours: float) -> dict:
    """Fees this position's range earned per unit of liquidity over a lookback window."""
    try:
        now = int(time.time())
        snap = snapshots.oldest_within(p["poolId"], p["tickLower"], p["tickUpper"], lookback_hours * 3600, now)
        snapshots.record(p["poolId"], p["tickLower"], p["tickUpper"], p["feeGrowthInside0"], p["feeGrowthInside1"], now)
        if snap:
            source, elapsed, pw = "snapshot", now - snap[0], (snap[1], snap[2])
        else:
            # The public RPC only serves a few minutes of history: short, low-confidence window.
            now_block = rpc.block_number()
            past_block = max(1, now_block - SHORT_WINDOW_BLOCKS)
            pool_id = bytes.fromhex(p["poolId"][2:])
            data = abi.call_data(
                "getFeeGrowthInside(bytes32,int24,int24)",
                pool_id,
                abi.enc_int(p["tickLower"]),
                abi.enc_int(p["tickUpper"]),
            )
            past = rpc.eth_calls([(STATE_VIEW, data)], past_block)[0]
            if not past:
                return {"available": False, "reason": "no snapshot yet and historical state not served by this RPC"}
            elapsed = rpc.block_timestamp(now_block) - rpc.block_timestamp(past_block)
            source, pw = "rpc-short-window", abi.words(past)
        if elapsed <= 0:
            return {"available": False, "reason": "could not measure elapsed time"}
        f0 = v4math.fees_owed(p["feeGrowthInside0"], pw[0], p["liquidity"])
        f1 = v4math.fees_owed(p["feeGrowthInside1"], pw[1], p["liquidity"])
        fees_usdg = _usdg_value(p, f0, f1)
        res = {
            "available": True,
            "source": source,
            "lowConfidence": source != "snapshot" or elapsed < 3600,
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
    price = v["total"] * (1 - haircut)
    fr = valuation.get("feeRate") or {}
    rent = None
    if fr.get("available") and fr.get("plausible") and fr.get("feesPerDayUSDG") is not None:
        rent = fr["feesPerDayUSDG"] * term_days * rent_share
    return {
        "available": True,
        "termDays": term_days,
        "inputs": {"haircut": haircut, "rentShareOfExpectedFees": rent_share},
        "marketValueUSDG": v["total"],
        "suggestedSalePriceUSDG": round(price, 2),
        "suggestedBuybackPriceUSDG": round(price, 2),
        "expectedFeesOverTermUSDG": round(fr["feesPerDayUSDG"] * term_days, 4) if rent is not None else None,
        "suggestedRentUSDG": round(rent, 4) if rent is not None else None,
        "eligibility": {
            "inRange": valuation["position"]["inRange"],
            "noSubscriber": not valuation["position"]["hasSubscriber"],
        },
        "disclaimer": "Indicative model output. Not a guarantee of funding or of resale value.",
    }
