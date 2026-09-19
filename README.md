<div align="center">

<img src="brand/logo-mark-512.png" alt="" width="104">

# Tenure

**Sell your Uniswap v4 position. Lease it back. Keep the fees.**

No loan. No liquidation. No oracle.

[![checks](https://github.com/TenureLP/tenure/actions/workflows/ci.yml/badge.svg)](https://github.com/TenureLP/tenure/actions/workflows/ci.yml)
![solidity](https://img.shields.io/badge/solidity-0.8.28-1B2B48)
![python](https://img.shields.io/badge/python-3.10%2B-1B2B48)
![dependencies](https://img.shields.io/badge/dependencies-none-F5B84B)
![status](https://img.shields.io/badge/status-prototype%2C%20unaudited-F5B84B)

</div>

---

A liquidity provider sells a position NFT to a financier for cash, leases it straight back for a
fixed rent, keeps collecting the pool's swap fees, and holds a promise from the financier to sell it
back at a price agreed upfront. **No debt is created at any point**, so there is nothing to
liquidate and no oracle anywhere in the deal path. If the lessee does not buy back before the grace
window closes, the financier simply takes delivery of the position they already own.

`Tenure` is a working name. **No contract is deployed on any chain**, nothing here is audited, and
none of it is offered to anyone. The two services run, read live chain state, and price positions;
that is all they do.

## How a deal runs

```
        SELLER                        VAULT                       FINANCIER
          │                             │                              │
          │ list(price, rent,           │                              │
          │      buyback, term)         │                              │
          ├────────── NFT ─────────────▶│                              │
          │                             │◀───────── fund() ────────────┤
          │◀─ price − rent − fee ───────┤  ownership recorded          │
          │                             │  rent escrowed               │
          │                             │                              │
          │    ┌────────────────────────┴───────────────────┐          │
          │    │  the lease: 7 or 21 days                   │          │
          │◀───┤  collectFees()  swap fees, as often as you │          │
          │    │                 like; liquidity untouchable│          │
          │    │  claimRent()    streams per usable second ─┼─────────▶│
          │    └────────────────────────┬───────────────────┘          │
          │                             │                              │
          │ buyBack()                   │                    release() │
          ├───── buyback price ────────▶│◀───── after term + grace ────┤
          │◀───────── NFT ──────────────┤──────────── NFT ────────────▶│
          │   unaccrued rent refunded   │   the position they own      │
```

Every payout is a balance the owed party withdraws. The vault has no owner and no upgrade path.

## What is in here

| Folder | What it is | State |
|---|---|---|
| [`lease-vault/`](lease-vault) | The contracts. `LeaseVault` is immutable and has no owner, no pause and no dependency on any other contract. | 60 tests, 5 against live chain state |
| [`lp-api/`](lp-api) | Position valuation over JSON-RPC, exact integer maths, behind an HTTP 402 gate that speaks x402 v2. | 69 tests, deployed, reads mainnet |
| [`app/`](app) | The deal flow as a page. Values a position against the live API today. | reads only, no contract to write to |
| [`landing/`](landing) | Static page and its signup endpoint. | deployed |
| [`brand/`](brand) | Logo, banner, teaser, all generated from one script. | done |

## Run everything

From WSL or Linux, with [Foundry](https://getfoundry.sh) and Python 3.10 or later. Nothing else to
install: the contracts use no external Solidity library, and the services use nothing outside the
standard library.

```bash
./check.sh
```

That builds the contracts, runs 60 Solidity tests including a stateful fuzz over random action
sequences, the Python tests, and the signup endpoint. Add `--fork` for five integration tests against
the real Uniswap v4 PositionManager on Robinhood Chain.

Price a real position, and get indicative terms for it:

```bash
cd lp-api && ./run.sh position 2908278 --quote
```

## Documentation

| Document | What it answers |
|---|---|
| [Specification](lease-vault/docs/SPEC.md) | The lifecycle, the economics of a deal, how rent and freezes work, the compliance analysis, the regulatory context |
| [Audit](docs/AUDIT.md) | What three adversarial reviews found, what was fixed, what was deliberately left alone |
| [Deploying](docs/DEPLOY.md) | The two services, their variables, and why the paywall refuses to start without a durable disk |
| [Contracts](lease-vault/README.md) | The blocker on tokenised stocks, the addresses, how to deploy |
| [API](lp-api/README.md) | Routes, the payment handshake, the fee-rate snapshots |
| [Paying for the API](docs/OLANAS.md) | The x402 handshake in full, and how it lines up with Olanas |
| [The token](docs/TOKEN.md) | TEN: the deployed address, the twenty-four powers it does not have, and what would have to be built to give it a purpose |

## What holds, and what does not

Proven by tests: the vault never owes more USDG than it holds, rent paid out never exceeds the rent
escrowed at funding, frozen time never exceeds its ceiling, a position is owed to at most one party,
the lessee can collect fees but can never withdraw liquidity, and a financier who takes delivery
receives a position they can actually unwind. On the services side, a payment cannot be spent twice,
a proof cannot be reused for another route, and a transaction hash alone buys nothing.

Not established: **no independent audit**, no deployment, no economic review of the lease terms under
stress, no formal verification. The vault takes no view on which pools are sound, which is a judgement whoever funds a deal has to make for themselves. The API
serves with a hardened `http.server`, which is sized for a prototype and not for volume.

## Why no dependencies

The contracts import no Solidity library, the API uses nothing outside the Python standard library,
and the signature recovery it needs is 90 lines in [`secp256k1.py`](lp-api/lpval/secp256k1.py),
checked against an independent implementation and against published vectors. The smaller the trusted
surface, the less there is to audit, and this is code people would trade against.
