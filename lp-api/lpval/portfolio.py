"""Every Uniswap v4 position a wallet holds, valued, with what can be said about each.

The PositionManager is not enumerable: it cannot say which tokens an address owns. So the list is
rebuilt from history. Every ERC-721 Transfer the PositionManager ever emitted *to* the address is a
position it held at some point; asking `ownerOf` of each keeps the ones it still holds.

What comes back is facts and options, never instructions. "Out of range, earning nothing" is a
reading of the chain; whether to move the range is the holder's call, and this module does not make
it for them.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from . import abi
from .rpc import REVERTED, UNAVAILABLE, RpcError, UpstreamError
from .valuation import POSM, PositionNotFound, quote, value_position

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DYNAMIC_FEE = 0x800000
MAX_POSITIONS = 40  # valued per request; the rest are listed by id with `truncated`
MAX_SCANNED = 200  # recent tokens gathered from a wallet too busy to list whole
MAX_LOG_QUERIES = 24
FULL_RANGE_TIMEOUT = 6.0  # a wallet with a few hundred transfers answers in one or two seconds
FIRST_WINDOW = 20_000  # blocks, about half an hour
WINDOW_TIMEOUT = 8.0
OWNER_BATCH = 25  # providers drop items from a large batch rather than refuse it
OWNER_WORKERS = 4
WANT_HELD = 60  # stop checking ownership once this many are found, newest first
SCAN_CAP = 600  # ids whose owner is checked at all
WORKERS = 4  # providers meter calls per second; eight valuations at once trip it

# ------------------------------------------------------------------ discovery


def _ids(logs):
    ids = set()
    for entry in logs:
        topics = entry.get("topics") or []
        if len(topics) == 4:
            ids.add(int(topics[3], 16))
    return ids


def _logs(rpc, params, endpoint, timeout):
    """One log query, with patience for a node that is only asking us to slow down. The public
    node rate-limits by address; a 429 is a request to wait, not a refusal of the query."""
    for attempt in range(3):
        try:
            return rpc.request_on("eth_getLogs", params, endpoint, timeout=timeout)
        except UpstreamError as exc:
            if "429" not in str(exc) or attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


_background = ThreadPoolExecutor(max_workers=4)


def _bounded(fn, seconds):
    """Wall clock, not socket inactivity: a node that trickles a large answer never trips a socket
    timeout, and one that takes forty seconds to list a bot's history is one to walk back instead.
    The abandoned query finishes in the background and is discarded."""
    future = _background.submit(fn)
    try:
        return future.result(timeout=seconds)
    except FutureTimeout:
        raise UpstreamError("the full history timed out")


def _too_many(exc) -> bool:
    text = str(exc).lower()
    return "exceeds limit" in text or "too many" in text or "timed out" in text


def received_token_ids(rpc, owner: str, want: int = MAX_SCANNED):
    """Every PositionManager token ever transferred to `owner`, newest first, and whether the list
    is the whole history.

    Asked of each endpoint in turn over the whole history. Providers disagree about how wide a log
    query may be: some refuse anything past a few blocks, and the public node answers the full
    range when the query is filtered by recipient. A refusal is about the endpoint, not the chain,
    so it moves on rather than failing.

    A wallet that has received more positions than a node will return in one answer (market-making
    bots mint dozens an hour) is walked backwards from the head instead, in windows that halve
    whenever the node refuses, until `want` recent tokens are found. Its answer is marked partial.
    """
    topic_to = "0x" + "0" * 24 + owner.lower()[2:]
    base = {"address": POSM, "topics": [TRANSFER, None, topic_to]}
    last = None
    for endpoint in rpc.endpoints:
        try:
            logs = _bounded(lambda: _logs(rpc, [dict(base, fromBlock="0x0", toBlock="latest")], endpoint,
                                          FULL_RANGE_TIMEOUT), FULL_RANGE_TIMEOUT)
        except (RpcError, UpstreamError) as exc:
            last = exc
            if _too_many(exc):
                return _walk_back(rpc, endpoint, base, want)
            continue
        if not isinstance(logs, list):
            last = UpstreamError("eth_getLogs did not return a list")
            continue
        return sorted(_ids(logs), reverse=True), True
    raise last or UpstreamError("no endpoint would serve the position history")


def _walk_back(rpc, endpoint, base, want):
    """Newest first, in windows that grow while they come back small and shrink when refused.
    A log query costs roughly in proportion to what it returns, so a bot's recent hour is cheap and
    its whole history is not."""
    head = rpc.block_number()
    window, top, ids, asked = FIRST_WINDOW, head, set(), 0
    while top > 0 and len(ids) < want and asked < MAX_LOG_QUERIES:
        bottom = max(0, top - window + 1)
        asked += 1
        try:
            logs = _logs(rpc, [dict(base, fromBlock=hex(bottom), toBlock=hex(top))], endpoint, WINDOW_TIMEOUT)
        except (RpcError, UpstreamError) as exc:
            if _too_many(exc) and window > 1:
                window = max(1, window // 4)
                continue
            raise
        found = _ids(logs if isinstance(logs, list) else [])
        ids |= found
        top = bottom - 1
        if len(found) < want // 4:
            window *= 2
    return sorted(ids, reverse=True)[:want], top <= 0


def still_owned(rpc, owner: str, token_ids, want: int = WANT_HELD, cap: int = SCAN_CAP):
    """Which of these the wallet holds right now, newest first, and whether every id was checked.

    A wallet that has touched three thousand positions is mostly history: asking `ownerOf` of all of
    them costs a minute, and the answer nobody is waiting for is the oldest. So ids are checked in
    order, in parallel, and the walk stops once `want` are found or `cap` have been asked about.

    A metered provider answers part of a batch and refuses the rest for going too fast. Only the
    refused items are asked again, after a pause and on the next endpoint along, instead of
    throwing away the answers that did come back.
    """
    if not token_ids:
        return [], True
    scanned = list(token_ids)[:cap]
    chunks = [scanned[i:i + OWNER_BATCH] for i in range(0, len(scanned), OWNER_BATCH)]
    answers = {}
    checked = 0

    def ask(chunk, endpoints):
        reqs = [("eth_call", [{"to": POSM, "data": abi.call_data("ownerOf(uint256)", abi.enc_uint(t))}, "latest"])
                for t in chunk]
        try:
            return dict(zip(chunk, rpc.batch(reqs, endpoints)))
        except UpstreamError:
            return {t: UNAVAILABLE for t in chunk}

    with ThreadPoolExecutor(max_workers=OWNER_WORKERS) as pool:
        for group in range(0, len(chunks), OWNER_WORKERS):
            batch = chunks[group:group + OWNER_WORKERS]
            for part in pool.map(lambda c: ask(c, None), batch):
                answers.update(part)
            checked = min(len(scanned), (group + OWNER_WORKERS) * OWNER_BATCH)
            held_so_far = sum(1 for t, raw in answers.items() if _is_owner(raw, owner))
            if held_so_far >= want:
                break

    # Whatever a provider refused for going too fast, asked once more further down the list.
    missing = [t for t in scanned[:checked] if answers.get(t) is UNAVAILABLE]
    if missing:
        time.sleep(0.6)
        for i in range(0, len(missing), OWNER_BATCH):
            answers.update(ask(missing[i:i + OWNER_BATCH], rpc.endpoints[1:] + rpc.endpoints[:1]))

    held = [t for t in scanned[:checked] if _is_owner(answers.get(t), owner)]
    return held, checked >= len(token_ids)


def _is_owner(raw, owner: str) -> bool:
    if not isinstance(raw, str) or not raw.startswith("0x") or len(raw) < 66:
        return False  # reverted (burnt), or never answered
    return abi.word_to_addr(int(raw[2:66], 16)) == owner.lower()


# ------------------------------------------------------------------ hooks

# Bit i of a hook's address says whether the PoolManager calls it at that point. Decoding it needs
# no call at all: in v4 what a hook may do is written into where it lives.
HOOK_FLAGS = [
    (13, "beforeInitialize"),
    (12, "afterInitialize"),
    (11, "beforeAddLiquidity"),
    (10, "afterAddLiquidity"),
    (9, "beforeRemoveLiquidity"),
    (8, "afterRemoveLiquidity"),
    (7, "beforeSwap"),
    (6, "afterSwap"),
    (5, "beforeDonate"),
    (4, "afterDonate"),
    (3, "beforeSwapReturnDelta"),
    (2, "afterSwapReturnDelta"),
    (1, "afterAddLiquidityReturnDelta"),
    (0, "afterRemoveLiquidityReturnDelta"),
]


def hook_permissions(hooks: str, key_fee_pips: int = 0) -> dict:
    """What a pool's hook is allowed to do, and what that means for a holder."""
    address = (hooks or "").lower()
    if not address or int(address, 16) == 0:
        return {"address": None, "permissions": [], "dynamicFee": False, "effects": []}
    bits = int(address, 16) & 0x3FFF
    perms = [name for bit, name in HOOK_FLAGS if bits >> bit & 1]
    effects = []
    if "afterRemoveLiquidityReturnDelta" in perms:
        effects.append({"level": "bad", "text": "can take a share of what is withdrawn, fees included"})
    elif "beforeRemoveLiquidity" in perms or "afterRemoveLiquidity" in perms:
        effects.append({"level": "warn", "text": "runs on every withdrawal and fee collection, and can refuse one"})
    if "afterAddLiquidityReturnDelta" in perms:
        effects.append({"level": "warn", "text": "can take a share of what is added"})
    elif "beforeAddLiquidity" in perms or "afterAddLiquidity" in perms:
        effects.append({"level": "info", "text": "runs when liquidity is added, and can refuse it"})
    if "beforeSwapReturnDelta" in perms or "afterSwapReturnDelta" in perms:
        effects.append({"level": "info", "text": "can change what a swap pays, so fee income may not follow volume"})
    dynamic = key_fee_pips == DYNAMIC_FEE
    if dynamic:
        effects.append({"level": "info", "text": "sets the swap fee itself, and can change it at any time"})
    if not effects:
        effects.append({"level": "info", "text": "observes the pool without touching liquidity or fees"})
    return {"address": address, "permissions": perms, "dynamicFee": dynamic, "effects": effects}


# ------------------------------------------------------------------ what can be said about one position


def _move(tick_from: int, tick_to: int) -> float:
    """Percent change in the price of token0 needed to go from one tick to another."""
    return (1.0001 ** (tick_to - tick_from) - 1) * 100


def diagnose(val: dict, lease: dict = None) -> list:
    """Findings, most pressing first. Each is a fact, with the options it opens."""
    pos, price = val["position"], val["price"]
    tick, tl, tu = price["tick"], pos["tickLower"], pos["tickUpper"]
    liquidity = int(pos["liquidity"])
    value = val.get("valueUSDG") or {}
    rate = val.get("feeRate") or {}
    t0, t1 = val["pool"]["token0"]["symbol"], val["pool"]["token1"]["symbol"]
    out = []

    if liquidity == 0:
        out.append({"kind": "empty", "level": "info", "title": "Empty position",
                    "detail": "It holds no liquidity, so it earns nothing. It can be burned, or have liquidity added back.",
                    "options": ["burn", "add-liquidity"]})
        return out

    if not pos["inRange"]:
        if tick < tl:
            side, need = t0, _move(tick, tl)
        else:
            side, need = t1, _move(tick, tu)
        out.append({"kind": "out-of-range", "level": "bad", "title": "Out of range, earning nothing",
                    "detail": "The price has left the range, so the position is entirely %s and collects no fees. "
                              "The price of %s would have to move %+.1f%% to bring it back." % (side, t0, need),
                    "options": ["rebalance", "wait", "withdraw"]})
    else:
        down, up = _move(tick, tl), _move(tick, tu)
        nearest = min(abs(down), abs(up))
        if nearest < 5:
            edge = "lower" if abs(down) < abs(up) else "upper"
            out.append({"kind": "near-edge", "level": "warn", "title": "Close to the %s edge" % edge,
                        "detail": "A %.1f%% move in the price of %s takes it out of range. Range: %+.1f%% to %+.1f%% from here."
                                  % (nearest, t0, down, up),
                        "options": ["widen", "watch"]})

    fees = value.get("fees")
    principal = value.get("principal")
    if fees and fees >= 1 and (not principal or fees >= principal * 0.005):
        out.append({"kind": "fees-waiting", "level": "info", "title": "%.2f USDG of fees to collect" % fees,
                    "detail": "Uncollected fees sit in the pool until they are taken. Collecting leaves the liquidity in place.",
                    "options": ["collect"]})

    if rate.get("available") and rate.get("plausible") and pos["inRange"]:
        apr = rate.get("feeAprPercent")
        if apr is not None and apr < 1:
            out.append({"kind": "low-yield", "level": "info", "title": "Earning %.2f%% a year" % apr,
                        "detail": "In range, but the fees over the last %.0f hours come to little against what it holds."
                                  % (rate.get("windowSeconds", 0) / 3600),
                        "options": ["compare", "rebalance"]})

    hooks = hook_permissions(val["pool"].get("hooks"), val["pool"].get("keyFeePips", 0))
    if hooks["address"]:
        worst = max(hooks["effects"], key=lambda e: ["info", "warn", "bad"].index(e["level"]))
        out.append({"kind": "hook", "level": worst["level"], "title": "Pool with a hook",
                    "detail": "The hook " + "; ".join(e["text"] for e in hooks["effects"]) + ".",
                    "options": ["inspect-hook"]})

    if pos["hasSubscriber"]:
        out.append({"kind": "subscriber", "level": "info", "title": "A subscriber is attached",
                    "detail": "Another contract is notified of every change to this position. It cannot be leased while one is attached.",
                    "options": ["unsubscribe"]})

    q = lease or {}
    # Only what the vault would accept: it refuses a listing out of range (OutOfRange) or with a
    # subscriber (HasSubscriber), whatever the quote says the position is worth.
    if q.get("available") and pos["inRange"] and not pos["hasSubscriber"]:
        out.append({"kind": "tenure", "level": "ok", "title": "Could raise %.2f USDG on Tenure" % q["suggestedSalePriceUSDG"],
                    "detail": "Sold and leased straight back for %d days at about %.2f USDG of rent, keeping the fees, "
                              "bought back at the same price." % (q["termDays"], q["suggestedRentUSDG"]),
                    "options": ["list"]})

    rank = {"bad": 0, "warn": 1, "ok": 2, "info": 3}
    out.sort(key=lambda f: rank[f["level"]])
    return out


# ------------------------------------------------------------------ the whole wallet


def _lease(val, q):
    """The quote, when the vault would take the listing; otherwise the reason it would not."""
    pos = val["position"]
    if not q.get("available"):
        return {"available": False, "reason": q.get("reason")}
    if not pos["inRange"]:
        return {"available": False, "reason": "out of range: the vault refuses the listing until it is back in range"}
    if pos["hasSubscriber"]:
        return {"available": False, "reason": "a subscriber is attached: the vault refuses the listing"}
    return q


def _one(rpc, token_id: int, lookback_hours: float, budget):
    if budget is not None:
        rpc.set_deadline(budget)
    try:
        val = None
        for attempt in range(2):
            try:
                val = value_position(rpc, token_id, lookback_hours=lookback_hours)
                break
            except PositionNotFound:
                return None
            except Exception:
                # A metered provider refuses a burst; the same reads a moment later usually pass.
                # One position the node still will not answer for is no reason to withhold the rest.
                left = rpc.remaining()
                if attempt == 0 and (left is None or left > 4):
                    time.sleep(1.2)
                    continue
                return {"tokenId": token_id, "unreadable": True}
    finally:
        if budget is not None:
            rpc.clear_deadline()
    q = quote(val)
    rate = val.get("feeRate") or {}
    value = val.get("valueUSDG") or {}
    return {
        "tokenId": token_id,
        "pool": {
            "poolId": val["pool"]["poolId"],
            "pair": "%s / %s" % (val["pool"]["token0"]["symbol"], val["pool"]["token1"]["symbol"]),
            "token0": val["pool"]["token0"],
            "token1": val["pool"]["token1"],
            "feePips": val["pool"]["currentLpFeePips"],
            "hooks": hook_permissions(val["pool"]["hooks"], val["pool"]["keyFeePips"]),
        },
        "position": val["position"],
        "price": {"tick": val["price"]["tick"], "token0InToken1": val["price"]["token0InToken1"]},
        "valueUSDG": val.get("valueUSDG"),
        "uncollectedFees": val["uncollectedFees"],
        "earning": {
            "feesPerDayUSDG": rate.get("feesPerDayUSDG") if rate.get("plausible") else None,
            "feeAprPercent": rate.get("feeAprPercent") if rate.get("plausible") else None,
            "source": rate.get("source"),
            "lowConfidence": rate.get("lowConfidence"),
        },
        "lease": _lease(val, q),
        "findings": diagnose(val, q),
        "_value": value.get("total") or 0.0,
        "_fees": value.get("fees") or 0.0,
    }


def portfolio(rpc, owner: str, lookback_hours: float = 24.0) -> dict:
    owner = owner.lower()
    received, whole_history = received_token_ids(rpc, owner)
    held, checked_all = still_owned(rpc, owner, received)
    complete = whole_history and checked_all
    valued_ids = held[:MAX_POSITIONS]
    budget = rpc.remaining()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = [r for r in pool.map(lambda t: _one(rpc, t, lookback_hours, budget), valued_ids) if r]
    rows = [r for r in results if not r.get("unreadable")]
    unreadable = [r["tokenId"] for r in results if r.get("unreadable")]

    rows.sort(key=lambda r: r["_value"], reverse=True)
    in_range = sum(1 for r in rows if r["position"]["inRange"] and int(r["position"]["liquidity"]) > 0)
    per_day = [r["earning"]["feesPerDayUSDG"] for r in rows if r["earning"]["feesPerDayUSDG"] is not None]
    summary = {
        "positions": len(held),
        "complete": complete,  # false: these are the most recent, not everything the wallet holds
        "valued": len(rows),
        "inRange": in_range,
        "outOfRange": sum(1 for r in rows if not r["position"]["inRange"] and int(r["position"]["liquidity"]) > 0),
        "empty": sum(1 for r in rows if int(r["position"]["liquidity"]) == 0),
        "valueUSDG": round(sum(r["_value"] for r in rows), 2),
        "uncollectedFeesUSDG": round(sum(r["_fees"] for r in rows), 2),
        "feesPerDayUSDG": round(sum(per_day), 2) if per_day else None,
        "attention": sum(1 for r in rows if any(f["level"] in ("bad", "warn") for f in r["findings"])),
        "note": "USDG figures cover pairs that include USDG only."
        + ("" if complete else " This wallet has received more positions than can be listed at once; these are its most recent."),
    }
    for r in rows:
        del r["_value"], r["_fees"]
    return {
        "owner": owner,
        "summary": summary,
        "positions": rows,
        "truncated": held[MAX_POSITIONS:],
        "unreadable": unreadable,
        "disclaimer": "Readings of the chain and options they open. Not advice.",
    }

