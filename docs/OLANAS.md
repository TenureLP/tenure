# Paying for this API, and the Olanas fit

[Olanas](https://github.com/olanass) is building onchain content payments on Robinhood Chain. This
service is a paid API on the same chain, speaking the same payment scheme. What follows is what a
client needs in order to pay, and an honest account of how much of the way there the two already
are.

Everything below was read from the Olanas documentation repository, not inferred.

## Why the fit is exact

| | Olanas | This API |
|---|---|---|
| Chain | Robinhood Chain, `4663` mainnet and `46630` testnet | the same |
| Scheme | `onchain-tx` | `onchain-tx` |
| Challenge | HTTP `402` naming network, amount, recipient, resource | the same, as an x402 v2 envelope |
| Proof header | `PAYMENT-SIGNATURE`, base64 JSON | the same, and raw JSON is also accepted |
| Receipt header | `PAYMENT-RESPONSE` | the same |
| Replay | a proof recovers the same purchase, never a different one | the same, enforced by a ledger on a mounted volume |

A client written against the Olanas payment flow already understands the shape of this one. No
adapter, no translation layer, no second wallet integration.

## The one difference, and why it exists

The Olanas proof is three fields:

```json
{ "scheme": "onchain-tx", "txHash": "0x…", "payer": "0x…" }
```

This API wants two more:

```json
{ "scheme": "onchain-tx", "txHash": "0x…", "payer": "0x…", "nonce": "…", "signature": "0x…" }
```

The reason is narrow. **A transaction hash is public the moment it is mined.** Anybody watching the
chain, or reading a block explorer, can copy the hash of a payment somebody else made and present it
as their own. For a paywall delivering a file that is a nuisance; for an API that meters requests it
is a way to spend other people's money.

So the challenge issues a `nonce` bound to the exact resource, and the proof has to carry a
`personal_sign` from the paying account over this text:

```
tenure payment
chain: 4663
to: 0x…
tx: 0x…
resource: /v1/position/2908254?lookbackHours=24
nonce: …
```

The account that signs must be the account that sent the transfer. The signature covers the path and
the nonce, never the `Host` header, which the caller controls. Only low-s signatures are accepted, so
one signature cannot be reshaped into a second valid one.

Both extra fields are announced in the challenge, under `accepts[0].extra`, with the exact text to
sign in `signThis`. A client that ignores `extra` fails closed rather than silently paying for
nothing.

## The handshake, end to end

The public deployment runs **free** today: `LPVAL_PAY_TO` is unset, so every route answers `200` and
none of this is needed. It is described because it is what turns on when a price is set.

**1. Ask, and read the price.**

```bash
curl -i https://api-production-9e87.up.railway.app/v1/position/2908254/quote
```

With a price configured this returns `402`, `WWW-Authenticate: x402`, and the envelope both as the
body and, base64-encoded, in `PAYMENT-REQUIRED`:

```json
{
  "x402Version": 2,
  "accepts": [{
    "scheme": "onchain-tx",
    "network": "eip155:4663",
    "amount": "1000000000000",
    "asset": "0x0000000000000000000000000000000000000000",
    "payTo": "0x…",
    "maxTimeoutSeconds": 900,
    "extra": {
      "proof": "confirmed-transaction+payer-signature",
      "minConfirmations": 3,
      "nonce": "…",
      "signThis": "tenure payment\nchain: 4663\nto: 0x…\ntx: <txHash>\nresource: …\nnonce: …"
    }
  }],
  "resource": { "path": "/v1/position/2908254/quote", "mimeType": "application/json" }
}
```

**2. Send the transfer.** `amount` wei of the chain's own coin to `payTo`. The zero address in
`asset` is how x402 names a native coin rather than a token.

**3. Sign.** Take `extra.signThis`, replace `<txHash>` with the hash of the transfer you just sent,
and `personal_sign` it with the sending account.

**4. Retry with the proof.**

```bash
curl -s https://api-production-9e87.up.railway.app/v1/position/2908254/quote \
  -H "PAYMENT-SIGNATURE: $(printf '%s' "$PROOF_JSON" | base64 -w0)"
```

`X402-PAYMENT` and `Authorization: x402 <proof>` are accepted as spellings of the same header,
because all three are in use. Being liberal about the envelope costs nothing; the strictness that
matters is in what the fields have to prove.

The answer carries `PAYMENT-RESPONSE`, a base64 receipt naming the transaction, the payer, the
recipient, the amount and the resource.

## What the chain has to agree with

Before a payment counts: the transaction is mined and succeeded, its recipient is `payTo`, its value
is at least `amount`, its sender is `payer`, it has at least `minConfirmations` confirmations, it is
not older than the age limit, and its hash has never been spent here before. The ledger of spent
payments sits on a mounted volume, and the service refuses to start if it does not — on an ephemeral
filesystem every spent payment is forgotten when the container is replaced, and each of them could
then be redeemed a second time.

If the request then fails on our side, the payment is released so the same proof can be retried
once. A caller never pays for our outage.

## The OpenAPI document

The Olanas endpoint reference closes with this:

> Before exposing a third-party API, add and validate an OpenAPI document so Mintlify can generate
> complete request schemas, responses, and an interactive playground.

Here is one. [`lp-api/openapi.yaml`](../lp-api/openapi.yaml) is OpenAPI 3.1, covers every route, the
`402` envelope, the proof, the receipt and every schema, and is **served by the running instance**:

```bash
curl https://api-production-9e87.up.railway.app/openapi.yaml
```

Served rather than copied, so the description cannot drift from the build that answers it. `check.sh`
fails if a route is served and undocumented, or documented and not served.

## What is true today, and what is not

**True:** the chain, the scheme, the headers and the proof shape line up. The document above exists,
validates, and is live. The service is running and answers real valuations.

**Not true yet:** nothing has been tested against an Olanas deployment. This service verifies proofs
itself and has never called `/facilitator/verify` or `/facilitator/settle`. Whether it should — a
resource server delegating verification to a facilitator is the more usual x402 arrangement — is an
open question and a reasonable first thing to try together.

**Not ours to decide:** Olanas's roadmap lists *documenting third-party integration interfaces*
under work still to come. Where a third-party API belongs in their product, and on what terms, is
theirs to say. This document exists so the answer does not have to start with a week of reading our
source.
