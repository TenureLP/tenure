"""Uniswap v3/v4 concentrated-liquidity math with exact integer arithmetic."""

Q96 = 1 << 96
Q128 = 1 << 128
U256 = 1 << 256
MIN_TICK = -887272
MAX_TICK = 887272

_TICK_CONSTS = [
    (0x2, 0xFFF97272373D413259A46990580E213A),
    (0x4, 0xFFF2E50F5F656932EF12357CF3C7FDCC),
    (0x8, 0xFFE5CACA7E10E4E61C3624EAA0941CD0),
    (0x10, 0xFFCB9843D60F6159C9DB58835C926644),
    (0x20, 0xFF973B41FA98C081472E6896DFB254C0),
    (0x40, 0xFF2EA16466C96A3843EC78B326B52861),
    (0x80, 0xFE5DEE046A99A2A811C461F1969C3053),
    (0x100, 0xFCBE86C7900A88AEDCFFC83B479AA3A4),
    (0x200, 0xF987A7253AC413176F2B074CF7815E54),
    (0x400, 0xF3392B0822B70005940C7A398E4B70F3),
    (0x800, 0xE7159475A2C29B7443B29C7FA6E889D9),
    (0x1000, 0xD097F3BDFD2022B8845AD8F792AA5825),
    (0x2000, 0xA9F746462D870FDF8A65DC1F90E061E5),
    (0x4000, 0x70D869A156D2A1B890BB3DF62BAF32F7),
    (0x8000, 0x31BE135F97D08FD981231505542FCFA6),
    (0x10000, 0x9AA508B5B7A84E1C677DE54F3E99BC9),
    (0x20000, 0x5D6AF8DEDB81196699C329225EE604),
    (0x40000, 0x2216E584F5FA1EA926041BEDFE98),
    (0x80000, 0x48A170391F7DC42444E8FA2),
]


def sqrt_ratio_at_tick(tick: int) -> int:
    """TickMath.getSqrtPriceAtTick: sqrt(1.0001^tick) as a Q64.96."""
    if tick < MIN_TICK or tick > MAX_TICK:
        raise ValueError("tick out of range")
    abs_tick = abs(tick)
    ratio = 0xFFFCB933BD6FAD37AA2D162D1A594001 if abs_tick & 1 else Q128
    for bit, const in _TICK_CONSTS:
        if abs_tick & bit:
            ratio = (ratio * const) >> 128
    if tick > 0:
        ratio = (U256 - 1) // ratio
    return (ratio >> 32) + (1 if ratio % (1 << 32) else 0)


def amounts_for_liquidity(sqrt_p: int, sqrt_a: int, sqrt_b: int, liquidity: int):
    """LiquidityAmounts.getAmountsForLiquidity (rounded down)."""
    if sqrt_a > sqrt_b:
        sqrt_a, sqrt_b = sqrt_b, sqrt_a
    if sqrt_p <= sqrt_a:
        amount0 = (liquidity << 96) * (sqrt_b - sqrt_a) // sqrt_b // sqrt_a
        amount1 = 0
    elif sqrt_p < sqrt_b:
        amount0 = (liquidity << 96) * (sqrt_b - sqrt_p) // sqrt_b // sqrt_p
        amount1 = liquidity * (sqrt_p - sqrt_a) // Q96
    else:
        amount0 = 0
        amount1 = liquidity * (sqrt_b - sqrt_a) // Q96
    return amount0, amount1


def fees_owed(fee_growth_inside: int, fee_growth_inside_last: int, liquidity: int) -> int:
    """Uncollected fees for one token. Fee growth accumulators wrap modulo 2^256 by design."""
    return ((fee_growth_inside - fee_growth_inside_last) % U256) * liquidity // Q128


def price_token0_in_token1(sqrt_p: int, dec0: int, dec1: int) -> float:
    """Human price of one whole token0 expressed in token1."""
    raw = (sqrt_p * sqrt_p) / (Q96 * Q96)
    return raw * (10 ** dec0) / (10 ** dec1)
