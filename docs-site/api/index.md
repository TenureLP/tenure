# Valuation API

A read-only HTTP API that values any Uniswap v4 position on Robinhood Chain mainnet and proposes
indicative terms for a sale-and-leaseback. It is what the app's **Value** screen calls.

**Base URL** `https://api-production-9e87.up.railway.app`

It never signs anything and never touches funds. Exact integer maths over JSON-RPC, Python standard
library only.

## Routes

| Route | Returns |
|---|---|
| `GET /health` | status, always free |
| `GET /v1/position/{tokenId}` | the valuation |
| `GET /v1/position/{tokenId}/quote` | the valuation plus indicative terms. See [quotes](/api/quotes) |
| `GET /v1/owner/{address}/positions` | every position a wallet holds, valued and diagnosed. See [your positions](/guide/positions) |
| `GET /openapi.yaml`, `/openapi.json` | the OpenAPI 3.1 description, served by the running build |

```bash
curl https://api-production-9e87.up.railway.app/v1/position/3093793
```

## What a valuation contains

| Field | What it is |
|---|---|
| `owner` | current holder of the NFT |
| `pool` | pool id, both tokens with symbol and decimals, fee, tick spacing, hook |
| `position` | tick range, liquidity, `inRange`, `hasSubscriber`, price bounds |
| `price` | the pool's current price and tick |
| `principal` | amount of each token held, exact |
| `uncollectedFees` | fees earned and not collected yet, exact |
| `valueUSDG` | principal, fees and total in USDG, when USDG is one of the two tokens |
| `feeRate` | fees per day in USDG and fee APR, measured over a window, with `source` and `lowConfidence` |

### Where the fee rate comes from

| `source` | Meaning |
|---|---|
| `snapshot` | our own recorded fee growth for that position |
| `rpc-archive` | the node served the state at the start of the full window |
| `rpc-short-window` | the node prunes history, so the rate covers only the last few minutes, flagged `lowConfidence` |

The window only ever shrinks, never grows: answering over more history than was asked for would
answer a different question.

## A whole wallet

```bash
curl https://api-production-9e87.up.railway.app/v1/owner/0x1283b0ee815f1066dd0eb435b4999aa2ae0ea1d1/positions
```

It rebuilds the wallet's positions from the PositionManager's transfer history, keeps the ones it
still holds, and values up to 40 of them.

| Field | What it is |
|---|---|
| `summary` | counts, total value, fees waiting, fees per day, and how many need a look |
| `summary.complete` | false when the wallet has received more positions than can be listed at once |
| `positions[].pool.hooks` | the hook's address, its permissions read from that address, and what they allow |
| `positions[].earning` | fees per day and APR over the window, with their source |
| `positions[].lease` | indicative Tenure terms, or why the vault would refuse the listing |
| `positions[].findings` | facts, most pressing first, each with the options it opens |
| `truncated`, `unreadable` | held but not valued here, and what the node would not answer for |

## Known limits

- A USDG value only when USDG is in the pair.
- The price is the pool's own. There is no cross-check against an external feed, so a manipulated
  pool is not detected.
- The fee rate assumes the current liquidity held over the whole window.
- Testnet has no USDG pools, so the API serves mainnet only.
