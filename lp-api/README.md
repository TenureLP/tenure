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

Every valuation also records a snapshot, which is what keeps a watchlist warm without an archive
node:

```bash
./run.sh snapshot 2908278 2908010 2908292
```

in an hourly cron.

## Environment

| Variable | Default |
|---|---|
| `LPVAL_RPC` | `https://rpc.mainnet.chain.robinhood.com` — an archive node here improves the fee rate |
| `LPVAL_PAY_TO` | empty, paywall off |
| `LPVAL_PRICE_WEI` | `1000000000000` |
| `LPVAL_MIN_CONFIRMATIONS` | `3` |
| `LPVAL_DB` | `lpval_payments.sqlite` |
| `LPVAL_SNAP_DB` | `lpval_snapshots.sqlite` |

Under WSL, put both databases outside `/mnt/c`, in `/tmp` or the Linux home: SQLite copes badly with
that filesystem.

## Known limits

- A USDG value only when USDG is in the pair. Pairs against WETH would need a reference pool.
- The price comes from the pool itself. There is no cross-check against the Chainlink feeds of the
  Stock Tokens yet, so a manipulated pool would not be detected.
- The fee rate assumes the current liquidity held over the whole window, and is wrong if the range's
  ticks were uninitialised at the start of it.
- Payment is in ETH. USDG is not supported yet.
- `http.server` is fine for a prototype and should be replaced before any production use.
