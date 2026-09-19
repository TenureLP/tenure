# lpval

Valuation API for Uniswap v4 liquidity positions on Robinhood Chain (4663), behind a pay-per-request
gate. Python, standard library only, nothing to install.

## What it returns

For a `tokenId` of the v4 PositionManager:

- the pool, both tokens, the hook, the fee;
- the range, the liquidity, whether the position is in range, whether it has a subscriber;
- the amount of each token and the uncollected fees, in exact integer arithmetic;
- the value in USDG when USDG is one of the two tokens;
- a fee rate measured over a window, with a confidence flag;
- on `/quote`, indicative sale-and-leaseback terms: price, buyback, rent.

## Running it

Everything runs from WSL, Python 3.10 or later.

```bash
./run.sh test
```

```bash
./run.sh find --scan 600 --min-usdg 1000
```

With `--wide`, only in-range positions with a very wide range are kept: the ones that stay eligible
long enough to test against.

```bash
./run.sh position 2908278 --quote
```

```bash
./run.sh serve --port 8402
```

End to end against the live chain, free mode then paid mode:

```bash
bash tests/smoke.sh
```

## Routes

| Route | Purpose |
|---|---|
| `GET /health` | status, always free |
| `GET /v1/position/<tokenId>` | valuation |
| `GET /v1/position/<tokenId>/quote?term=7&haircut=0.2&rentShare=0.5&lookbackHours=24` | valuation plus indicative terms |

## The paywall

Off by default. To turn it on:

```bash
LPVAL_PAY_TO=0xYourAddress LPVAL_PRICE_WEI=1000000000000 ./run.sh serve
```

With no proof, paid routes answer 402 with an **x402 version 2** envelope: an `accepts` array
carrying the network in CAIP-2 notation, the amount, the asset, the address to pay and a timeout. The
same envelope is returned base64-encoded in the `PAYMENT-REQUIRED` header, so any client built for
the standard understands the shape.

The policy inside is stricter than the usual `confirmed-transaction` proof, and says so in
`accepts[0].extra`: the payer's signature is required too. The client sends the ETH, signs the
`signThis` text with the account that paid, then retries with the proof in `PAYMENT-SIGNATURE`,
`X402-PAYMENT` or `Authorization: x402 ...`, as raw JSON or base64:

```
{"scheme":"onchain-tx","txHash":"0x..","payer":"0x..","nonce":"..","signature":"0x.."}
```

The signature is the point. A transaction hash is public the moment it is mined: if the hash alone
bought a response, anyone watching the chain could spend a customer's payment before they did, and
any transfer that happened to reach the address would be a free request. A client that ignores
`extra` fails, by design.

The signed text covers the route path, never the `Host` header, which the caller controls.

Checked before a payment counts: recipient, sender, amount, success, depth (3 blocks by default),
age (an hour at most), a nonce valid for that route, and a hash never spent before. If the request
then fails on our side, the payment is released so the client can retry.

The whole path, tested against the live chain without moving any funds:

```bash
python3 tests/paywall_live.py
```

## Fee rate and snapshots

The rate is read over the window the caller asked for, from the best source available, and every
answer says which one it used:

| `source` | What it means |
|---|---|
| `snapshot` | Our own recorded fee growth, from `LPVAL_SNAP_DB` |
| `rpc-archive` | The node served the state at the start of the full window |
| `rpc-short-window` | The node prunes, so the rate covers about the last eight minutes |

Point `LPVAL_RPC` at an archive node and a fee rate is worth quoting on the very first request,
before any snapshot exists. Without one, the public node keeps roughly ten minutes of history and
the result is marked `lowConfidence`; a quote carries the same flag as `feeRateLowConfidence`. The
fallback only ever shrinks the window — answering over more history than was asked for would answer
a different question, and callers price deals on the answer.

A historical read is retried against every endpoint before the window is allowed to shrink. "I
cannot serve that state" is a fact about one node, not about the chain: a provider fronting a pool
answers it from some of its nodes and not others. Measured on one of ours, the identical call
succeeded nine times in twelve, so taking the first refusal at face value handed the same position
a 24-hour rate or an eight-minute one depending on the draw — and a rent quoted off the difference.

Every valuation also records a snapshot, which is what keeps a watchlist warm without an archive
node:

```bash
./run.sh snapshot 2908278 2908010 2908292
```

in an hourly cron.

## Machine-readable description

[`openapi.yaml`](openapi.yaml) is OpenAPI 3.1 and covers every route, the `402` envelope, the
proof, the receipt and every schema. The running instance serves it:

```bash
curl https://api-production-9e87.up.railway.app/openapi.yaml
```

Served rather than copied, so it cannot drift from the build that answers. `check.sh` fails if a
route is served and undocumented, or documented and not served.

[`../docs/OLANAS.md`](../docs/OLANAS.md) walks the payment handshake end to end and sets it beside
the Olanas flow, which uses the same scheme on the same chain.

## Environment

| Variable | Default |
|---|---|
| `LPVAL_RPC` | `https://rpc.mainnet.chain.robinhood.com` — one or more endpoints, see below |
| `LPVAL_PAY_TO` | empty, paywall off |
| `LPVAL_PRICE_WEI` | `1000000000000` |
| `LPVAL_MIN_CONFIRMATIONS` | `3` |
| `LPVAL_DB` | `lpval_payments.sqlite` |
| `LPVAL_SNAP_DB` | `lpval_snapshots.sqlite` |

Under WSL, put both databases outside `/mnt/c`, in `/tmp` or the Linux home: SQLite copes badly with
that filesystem.

### Several RPC endpoints

`LPVAL_RPC` takes a whitespace-separated list. Entries are tried **in order**, and the ones after
the first are what it falls back to. Each may carry headers, because providers disagree about where
the key goes — a path segment for some, a header for others:

```
LPVAL_RPC="https://archive.example/v2/KEY  https://pool.example|x-api-key:KEY  https://public.example"
```

Order it deliberately. Endpoints are not spread round-robin: providers sit at slightly different
heights, and a read at `latest` landing on a node a few blocks behind the one that just gave us a
block number reads state that does not match it. Put the most reliable archive node first.

**Every form of the key is a secret**, in the url or in a header. The client takes all of them back
out of error text before it reaches a caller, and only hostnames are ever logged.

## Known limits

- A USDG value only when USDG is in the pair. Pairs against WETH would need a reference pool.
- The price comes from the pool itself. There is no cross-check against the Chainlink feeds of the
  Stock Tokens yet, so a manipulated pool would not be detected.
- The fee rate assumes the current liquidity held over the whole window, and is wrong if the range's
  ticks were uninitialised at the start of it.
- Payment is in ETH. USDG is not supported yet.
- `http.server` is fine for a prototype and should be replaced before any production use.
