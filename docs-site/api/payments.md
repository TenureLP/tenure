# Paying per request

The API can sit behind an HTTP 402 gate that speaks **x402 version 2**, so an agent can pay for each
request with no account and no API key. The public deployment currently runs free.

## The handshake

1. **Ask.** A paid route with no proof answers `402 Payment Required`, with an x402 v2 envelope: an
   `accepts` array carrying the network in CAIP-2 form, the amount, the asset, the address to pay and a
   timeout. The same envelope is sent base64-encoded in the `PAYMENT-REQUIRED` header.
2. **Pay.** Send the amount in ETH to the address given.
3. **Sign.** Sign the `signThis` text from the envelope with the account that paid.
4. **Retry** with the proof in `PAYMENT-SIGNATURE`, `X402-PAYMENT` or `Authorization: x402 …`, as raw
   JSON or base64:

```json
{"scheme":"onchain-tx","txHash":"0x…","payer":"0x…","nonce":"…","signature":"0x…"}
```

## Why a signature, not just the hash

A transaction hash is public the moment it is mined. If the hash alone bought a response, anyone
watching the chain could spend a customer's payment before they did, and any transfer that happened to
reach the address would be a free request. So `accepts[0].extra` asks for the payer's signature too,
and a client that ignores it fails, by design.

The signed text covers the route path, never the `Host` header, which the caller controls.

## What is checked

Before a payment counts: recipient, sender, amount, success, depth (3 blocks by default), age (an hour
at most), a nonce valid for that route, and a hash never spent before. If the request then fails on the
server's side, the payment is released so the client can retry.

## Running your own

```bash
cd lp-api
LPVAL_PAY_TO=0xYourAddress LPVAL_PRICE_WEI=1000000000000 ./run.sh serve
```

| Variable | Default |
|---|---|
| `LPVAL_RPC` | the public RPC. Accepts several endpoints, tried in order |
| `LPVAL_PAY_TO` | empty, paywall off |
| `LPVAL_PRICE_WEI` | `1000000000000` |
| `LPVAL_MIN_CONFIRMATIONS` | `3` |
| `LPVAL_DB` | `lpval_payments.sqlite` |
| `LPVAL_SNAP_DB` | `lpval_snapshots.sqlite` |
