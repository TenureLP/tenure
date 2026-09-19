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

## Listing on the launchpad

`olanas.xyz` is an API launchpad: paste an endpoint, set a price per request, sign, and it handles
the payment wall, settlement, the public listing and the analytics. It charges no platform fee.

**Read this before turning our own paywall on.** The launch form says it keeps the submitted URL
private and puts a protected public gateway in front of it. Their gateway is the thing collecting
payment. An upstream that also demands payment would mean a caller pays twice, and the second
charge would be the one they never agreed to. The public deployment runs free, with `LPVAL_PAY_TO`
unset, which is exactly the shape that arrangement wants. Leave it that way while listed there, or
list a separate instance.

What the form asks for, and what was put in it:

| Field | Value |
|---|---|
| API endpoint | `https://api-production-9e87.up.railway.app` |
| Product name | Tenure position valuation |
| Category | Finance |
| One-line description | Prices any Uniswap v4 liquidity position on Robinhood Chain, and proposes sale-and-leaseback terms for it. |
| OpenAPI schema | [`lp-api/openapi.json`](../lp-api/openapi.json), or download `/openapi.json` from the live service |
| What it does | **Read data (GET)** only. Nothing here writes. |
| Logo | `brand/logo-avatar-1024.png`, square, 410 KB against a 512 KB limit |
| Payment network | Robinhood Chain, `4663`, fixed |
| Demo video | optional, and there is nothing worth showing yet |

The schema field is optional on the form and the reason to fill it is written next to it: it is what
lets an agent understand the inputs and responses without a human in the loop. It takes JSON and
caps at 256 KB; ours is 26 KB.

On price, their own example runs at 0.002 USDC per request. The service's default is
`1000000000000` wei, about a third of a US cent at present, which is the same order. USDG is the
friendlier unit to price in, since it is the unit every valuation is already denominated in.

Publishing needs a wallet connection and a signature proving ownership of the endpoint. That is not
something this repository can or should do for anybody: it is the operator's key and the operator's
claim.

## It is listed

Published on 19 September 2026 and verified from outside:

| | |
|---|---|
| Page | `olanas.xyz/services/tenure-position-valuation` |
| Service id | `svc_29f06fc7293c7ae6de47fac8` |
| Gateway | `https://olanas.xyz/x402/tenure-position-valuation` |
| Status | `live`, price `0.003` USDG, `GET` only, chain `4663` |

At the time of listing, `/api/services` reported one service in total. The gateway answers a proper
x402 version 2 challenge: scheme `onchain-tx`, network `eip155:4663`, 0.003 USDG. Their facilitator
reports `feeBps: 0`, which matches what the site claims.

The two hashes inside the signed launch message were checked against the files that were uploaded.
The logo hash is the SHA-256 of `brand/logo-avatar-1024.png`. The schema hash is the SHA-256 of
`lp-api/openapi.json` **re-serialised compactly** — their form parses the document and stringifies it
before hashing, which is why it does not match the file on disk. Nothing was substituted.

They republish the document with the server list rewritten to their gateway, our local development
server dropped, and an `x-olanas-payment` extension added. That is what a gateway should do.

### One thing to report back

The `servers` entry in the document they publish is `http://olanas.xyz/x402/...`, not `https`. That
URL answers `308 Permanent Redirect` to the https one, so a browser is fine. Two kinds of client are
not:

- one that does not follow redirects, which is a reasonable posture for a client carrying payment
  proofs, and is what the RPC client in this repository does;
- one that follows the redirect but drops headers across it, which several HTTP libraries do by
  default. That silently loses `PAYMENT-SIGNATURE`, and the caller sees a `402` they have already
  paid for.

Nothing here is broken by it today, because the gateway itself serves https correctly. It is the
published description that points at the wrong scheme.

## What is true today, and what is not

**True:** the chain, the scheme, the headers and the proof shape line up. The document above exists,
validates, and is live. The service is running and answers real valuations.

**Not true yet:** nothing has been tested against an Olanas deployment. This service verifies proofs
itself and has never called `/facilitator/verify` or `/facilitator/settle`. Whether it should — a
resource server delegating verification to a facilitator is the more usual x402 arrangement — is an
open question and a reasonable first thing to try together.

**Not ours to decide:** Olanas's roadmap lists *documenting third-party integration interfaces*
under work still to come, and the launchpad is described on their own site as a beta. Where a
third-party API belongs in their product, and on what terms, is theirs to say. This document exists
so the answer does not have to start with a week of reading our source.

Their account is [@Olanas_Infra](https://x.com/Olanas_Infra), and the token contract they publish is
`0x9400eB66B1320050A68F25A624985a674F033902` on Robinhood Chain. Verify it against
[their documentation](https://github.com/olanass/docs) rather than against this file.
