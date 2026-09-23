# What Uniswap v4 hooks do to liquidity on Robinhood Chain

A census taken on 23 September 2026, block 70,452,937. Public on-chain data only; every figure
below can be recounted with the three scripts in this folder, a public RPC and no key.

```bash
python3 census.py      # every PoolManager Initialize event  -> pools.jsonl   (870,453 lines)
python3 sample.py      # 2,000 random position ids           -> sample.jsonl
curl -sL -o hooklist.json https://raw.githubusercontent.com/Uniswap/hooklist/main/hooklist.json
python3 analyse.py     # the totals below
```

`census.py` splits its block windows in half whenever the node refuses more than 10,000 logs.
`sample.py` draws ids uniformly from every position the PositionManager has minted, with a fixed
seed, so a rerun on the same block draws the same ids. The data files are not committed.

## Pools

| | |
|---|---|
| v4 pools initialised, 22 May to 23 September | **870,453** |
| since 6 July | 869,794, about 11,000 a day |
| with a hook | **298,927**, 34.3 % |
| with a dynamic fee, which only a hook can set | 196,488, 22.6 % |
| paired with ETH / with USDG | 49.2 % / 22.7 % |
| distinct hook contracts | **22,757** |
| of them in Uniswap's hook registry | 1,142, holding 261,724 hooked pools (87.6 %) |
| not in the registry | 21,615, holding 37,203 hooked pools |

What the hooks of those 298,927 pools may do, decoded from the low 14 bits of each hook address as
the PoolManager reads them. A pool can hold several.

| permission | pools | share |
|---|---|---|
| change what a swap pays (`beforeSwap`/`afterSwap` return delta) | 274,305 | 91.8 % |
| run on every deposit, and refuse one | 236,441 | 79.1 % |
| run on every withdrawal and fee collection, and refuse one | 208,039 | 69.6 % |
| take a share of what is withdrawn (`afterRemoveLiquidity` return delta) | 1,179 | 0.4 % |

The biggest hook, **Doppler**, runs 172,635 pools: 57.8 % of hooked pools. The ten biggest run
78.7 %. Most of the top ten carry the names of token-launch platforms in the registry: Doppler, Clanker
Static Fee Hook (V2), V2MemeHook, CashCatHookV2, UniversalKlikHook, LunchTaxHookPair, Flaunch
PositionManager, PairV4Hook, and two contracts named LaunchHook.

Of the 1,164 Robinhood Chain entries in the registry, 4 link an audit and 35 are marked
upgradeable. A missing link is not proof of a missing audit, and absence from the registry says
nothing either way about safety.

## Positions

2,000 ids drawn from 3,159,229 minted; 1,975 readable.

| | share | 95 % margin |
|---|---|---|
| still exist (the rest were burned) | 59.7 % | ±2.2 |
| still hold liquidity | 13.5 % | ±1.5 |
| hold liquidity inside their range | 9.1 % | ±1.3 |

Of the 264 that hold liquidity and whose pool could be read:

- 58 % span more than a tenfold move in price; 4 % are narrower than 10 %, and 9 of those 10 were
  out of range.
- 22 % run to the edge of the tick space on at least one side: full-range or token-launch liquidity.
- 96 sit in pools with a hook. 55 of those belong to a single contract, all in pools run by the
  Clanker hook; 53 of the 55 were out of range.

## Context

Hook bugs have already cost LPs money: Cork (May 2025, about $11 million) and Bunni (September
2025, $8.4 million). Trail of Bits' guide to building secure hooks (July 2026) lists withdrawal
blocking, delta accounting and dynamic fee manipulation among the classes of bug to design against.
