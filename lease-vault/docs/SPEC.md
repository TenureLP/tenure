# Lease Vault, specification v0.1

Target network: Robinhood Chain (4663), Uniswap v4.

## 1. Purpose

Give a Uniswap v4 liquidity provider immediate liquidity with no loan, no interest and no
liquidation, under the conditions AAOIFI sets for ijarah muntahia bittamleek (standard 9) and its
2008 statement on sukuk. Keep the product experience of a collateralised loan (cash now, a choice at
maturity, no oracle) while changing what the contract legally is.

Out of scope for v1: Uniswap v3 positions, buyback at market value, an aggregating vault on the
financier side, synthetic tokenised equities.

## 2. Parties

| Party | Role | What they hold |
|---|---|---|
| Seller, then lessee | The liquidity provider who wants cash | The right to use the position (its swap fees) and a promise to sell it back |
| Financier | The one who brings the cash | Ownership of the position NFT, transferable, and a fixed rent |
| Screening list | A published opinion, owner-managed | Which pools its author considers fit to deal in. The vault never reads it and it has no power over any deal |
| Vault | Execution, no owner | Escrow of the NFTs and the USDG, balances to withdraw |

## 3. Lifecycle

```
None --list()--> Listed --fund()--> Active --buyBack()--> BoughtBack
                   |                   |
                   +--cancel()-->      +--release()  (after term + grace) --> Released
                   Cancelled
```

While `Active`:

- `collectFees`: lessee only, until the term ends. The v4 actions emitted are `DECREASE_LIQUIDITY`
  with zero liquidity, then `TAKE_PAIR` to the lessee. The vault never encodes any other action.
- `claimRent`: anyone, credits the financier with the rent accrued so far.
- `buyBack`: lessee, from funding until the financier has taken delivery. They pay the buyback price,
  get the NFT back, and unaccrued rent is refunded to them.
- `release`: financier, from term plus grace. They take delivery of the NFT. Rent unaccrued because
  of a freeze is refunded to the lessee.
- `transferFinancierPosition`: the financier sells their ownership on. The lease continues. Accrued
  rent is settled to the outgoing financier first. Never to the lessee.
- `checkpointFreeze`: anyone, records that the underlying froze or unfroze.

Endgame: `withdrawUSDG` and `withdrawPosition` are the only ways an asset leaves, always pulled by
whoever is owed it.

## 4. The economics of one deal

An example, USDG having 6 decimals.

| Parameter | Value |
|---|---|
| Market value of the position | 2,280 USDG |
| Sale price | 1,815 USDG |
| Total rent, 7 days | 9 USDG |
| Buyback price | 1,815 USDG |
| Builder fee, if a front end brought the deal | 0 by default |
| Received by the seller at funding | 1,806 USDG |

The financier earns 9 USDG of rent if the lease runs its course, about 0.5% over 7 days, plus 1,815
at the buyback. If there is no buyback they keep a position worth whatever it is worth. The seller
paid 9 USDG of rent for 1,815 USDG of cash, while collecting the week's swap fees. The vault takes
nothing in between; see section 8 on where a fee would belong instead.

Enforced in code: the rent must be below the price, neither the rent nor the buyback price may
be zero, and **the buyback price may not exceed the sale price**. The financier is paid for the use
of the asset, never for the passage of time; a buyback above the sale price would be a guaranteed
spread on top of the rent, which is a financing cost wearing the clothes of a sale. The seller sets
that number, so nothing would stop financiers from funding only the listings that carry a spread —
and there is no owner here to forbid it afterwards, so the code does it. Below the sale price is
allowed: only the financier is worse off, and only by their own choice to fund it.

The interface suggests a sale price near market value; the discount is negotiated, not imposed.

## 5. Rent, and freezes of the underlying

Rent is a fixed amount for the term, prepaid into escrow, streaming linearly per usable second. It
never compounds and the contract never annualises it.

The lessor carries an owner's risk. In v1 that risk is expressed through freezes: on every
interaction and on every `checkpointFreeze`, the vault asks each token of the pair whether it is
paused, using the probe the seller named in the terms. Frozen seconds are removed from the rent
base and refunded to the lessee at settlement. The calendar term itself does not stretch.

Two bounds sit on that.

A freeze counts for at most `MAX_FREEZE_GAP` (6 hours) beyond the last time it was actually
observed, so nobody can open one and let it run unattended.

On top of that, a deal credits at most `maxFrozenBps` of its term as frozen. The seller names that
figure in the terms and the vault refuses anything above `MAX_FROZEN_BPS`, a constant at 50%.
Sampling cannot distinguish "frozen all week, observed every six hours" from "halted for one second
at each of those instants", so without a total ceiling a lessee who checkpoints during repeated
brief halts could wipe out the rent for a few dozen cheap transactions. A high figure suits the
seller, who chooses it, which is exactly why the ceiling is a constant rather than a setting: the
financier reads the offer, reads this file once, and needs nobody's word for the rest.

The cost points the other way: a pair that genuinely halts for longer than the figure agreed makes
the lessee pay rent for time the asset was unusable. For crypto pairs that never halt, 25% is
already slack. Tokenised equities halt every night and every weekend, which is past even the 50%
ceiling, so financing one means either accepting that or redesigning the freeze evidence entirely.

Known limit: a position destroyed by an exploit in the pool is not detectable generically on chain.
In that case the financier owns a worthless position and the lessee owes nothing more, which is the
expected outcome for a lease.

## 6. How the design maps to the fiqh requirements

| Requirement | Mechanism in the code | Reference |
|---|---|---|
| A real sale, with ownership transferred | The NFT is recorded to the financier at `fund`, transferable via `transferFinancierPosition`, delivered by `release` with no "claim" step | AAOIFI 9, 3/1; 2008 sukuk statement |
| The lessor carries the asset risk | Rent suspended while frozen, the unaccrued part refunded; no claim on the lessee if the asset is destroyed | AAOIFI 9, 5/1/7 |
| Rent for a real usufruct | The lessee collects the swap fees through `collectFees`; the position must be in range at listing and at funding, and hold some liquidity | AAOIFI 9, 5/1 |
| No 'inah | Sale and lease are two acts settled in order inside `fund`; the financier cannot transfer to the lessee except through `buyBack`. The `SelfDeal` check compares addresses: it stops the obvious self-funding, not a seller using a second address. No on-chain check can do better, and the committee should weigh that | OIC Fiqh Academy, res. 66; AAOIFI 9, 3/2 |
| Buyback by unilateral promise, at a price fixed in advance and never above the sale price | `buyBack` at `buybackPrice`, exercised at the lessee's sole discretion; `list` refuses a buyback above the price, so the financier can never earn a spread on the capital | AAOIFI 2008 statement on ijarah sukuk, provided the lessor bears total loss |
| No ghalaq ar-rahn | There is no pledge: the financier keeps nothing, they take delivery of what is theirs | Hadith "la yughlaq ar-rahn" |
| No fee taken between the parties | The vault charges nothing and pays no address of its own. Each side may name a builder and pay them a flat amount out of its own money, for bringing them the deal | AAOIFI 19 on qard fees, by analogy; ujrah for a service rendered |
| No oracle, no liquidation | No price is read in the deal path; `StateView` only checks the range at listing and at funding | Product principle |
| Permissible assets | Not the vault's business. A screening list carries `assetClass` and `screeningRef` per pool, and whoever funds a deal decides what to consult | AAOIFI 21 screening for equities |

Open points for a committee to settle:

1. Rent shown by the interface as a percentage of the price, even though the contract only knows an
   amount. AAOIFI allows rent to be indexed; presentation does not change the nature of the contract.
2. A buyback at a fixed price, capped at the sale price. Allowed by the 2008 AAOIFI statement for
   ijarah sukuk, criticised by some scholars. The alternative, a buyback at market value computed
   from pool state, exposes the deal to price manipulation in shallow pools. The cap removes the
   worst reading of the fixed price, that it hides a return on capital, but not the objection to
   fixing it at all.
3. Refunding unaccrued rent on an early buyback. Consistent with a lease that ends when ownership
   transfers; some committees prefer the buyback price plus the remaining rent.
4. Whether an LP position on a crypto pair counts as productive. Swap fees are payment for a market
   service; permissibility depends on both tokens and on the pool containing no lending mechanism.

## 6b. Why the vault is this small

`LeaseVault` has no owner, no pause, no upgrade path and no reference to any other contract. Once
deployed there is nothing left to configure and nobody left to ask. Every term of a deal is proposed
by the seller within bounds that are constants in the source, and accepted by the financier in the
act of funding it. There is no third party to the agreement.

That costs something and it is worth naming. The vault holds no view on which pools deserve to be
dealt in, so the compliance work in section 6 is not enforced by the bottom layer. It cannot be: an
allowlist welded into an immutable contract is either frozen forever or governed by somebody, and
governed means an address that can strand a position a seller has already handed over.

So the judgement moves to where the money is. A financier consults whatever they trust before
funding. `ScreeningList` is one such published opinion, owner-managed, recording `assetClass` and
`screeningRef` per pool; the vault never reads it, and removing a pool from it stops nothing already
running. Anyone who disagrees deploys their own list and points their own capital at it.

The layer above is where the product lives, and where a fee belongs: a vault pooling financier
capital that funds only what its curator approves, a front end that declines to show the rest, a
matching service. Each of those renders a service somebody can price. A toll on the primitive itself
could never be removed once it is immutable, and would be harder to defend as a fee at cost.

### Builder codes

The vault carries one thing that looks like a fee and is not, borrowed from Hyperliquid: each side
may name a **builder** and a flat amount in USDG to pay them.

- The seller names theirs in the terms. It comes out of the proceeds they were already agreeing to,
  and the vault refuses terms where rent plus that fee leaves the seller nothing.
- The financier names theirs when funding, and pays it **on top** of the price, so it can never
  touch what the seller was promised.
- Name nobody and nothing is charged. This is the default and it is what `fund(dealId)` does.
- Neither fee reaches this contract. There is no address in the vault that collects anything.

`MAX_BUILDER_FEE_DIVISOR` caps each side at a hundredth of the sale price. The cap is not there to
protect the protocol, which takes nothing either way; it is there because the party paying rarely
builds the transaction they sign, and a front end filling that field in on their behalf should not
be able to help itself to an unbounded share.

The distinction that makes this compatible with an immutable contract: a **toll** is taken from
everyone, goes to a fixed address and cannot be removed; a **builder fee** is chosen by the party
paying it, goes to whoever that party names, and is zero by default. The first is governance wearing
a different hat. The second is two people agreeing to pay their own agents.

It is also the easier one to defend in section 6. It is a flat amount, not a share of principal, and
it buys something real: the interface, the screening, the introduction. A percentage ceiling bounds
abuse without making the fee itself a percentage of the money at stake.

Not borrowed: Hyperliquid's HIP-3 deployers, who stand up a market and take a cut of everything
traded on it. That needs the base layer to know who operates what, which is per-market governance by
another name. The equivalent here is the curated vault one layer up, whose curator earns from their
own depositors because they carry the risk of their own screening.

## 7. Regulatory context, as of September 2026

**SEC innovation exemption.** A temporary five-year order exempting Tokenized Securities Venues from
the definition of an exchange, for trading tokenised NMS stock through permissioned AMMs, with a
conditional exemption from the dealer definition for liquidity providers using proprietary capital.
Conditions: permissioned participants, auditable contracts on a public ledger, halts synchronised
with the primary market, issuer notification, symbol and volume caps, and no financing offered by
the venue. Only tokenised equities carrying the same rights as a share qualify; synthetics are out.

What that means here:

- LP positions in a venue's pools would be held by the vault, an ownerless contract. Whether a
  contract can be a permissioned participant, and whether the dealer exemption covers a financier
  buying an existing position rather than supplying liquidity themselves, both need checking.
- The vault is not a venue and offers no financing in the sense of the order: there is no loan and no
  margin. The exact characterisation still needs counsel.
- Robinhood's current Stock Tokens are Jersey debt securities barred from US persons. They are out of
  scope and must not be allowlisted.

**CFTC staff letter 26-25.** No-action for passive software providers who hold no funds, exercise no
discretion, route no orders and are not paid on volume. The vault and a front end that displays it
meet those tests, which is an argument for a neutral interface paid a flat fee. That letter concerns
introducing-broker registration on the derivatives side, not securities.

## 8. Security

An adversarial audit was run in September 2026; what it found and what was changed are in
`../../docs/AUDIT.md`. Two consequences belong here rather than there: a freeze only counts six hours
past the last sighting, and fees earned during the grace window go to whoever takes delivery, the
lease being over.

- Reentrancy: a simple lock on every function that moves an asset. NFT transfers use `transferFrom`,
  with no receive hook.
- Registry: its parameters are read at listing and frozen into the deal, so a later change touches no
  active deal. It can never move an asset. `fund` re-reads only the admission checks, which cannot
  affect a deal that is already active.
- v4 actions: the vault can only encode fee collection. No other liquidity change is possible while
  the NFT is in the vault.
- v4 subscribers: rejected at listing; v4 unsubscribes on transfer anyway.
- Pausable tokens: `collectFees` fails cleanly while a token is frozen, and the rent is suspended.
- The freeze probe runs under a fixed gas stipend and copies at most one word, so a token cannot
  strand a deal by answering with megabytes. A probe that reverts, or that succeeds with nothing to
  say, means the token has no freeze switch; only a non-empty answer in the wrong shape is read as
  frozen. The stipend is 100,000 gas, generous enough for a proxy with several cold reads, because
  the defence against an oversized answer is the copy bound rather than a tight budget.
- `fund` re-checks that the position is in range, which lets a third party delay a funding by moving
  the spot tick out of the range for one block. That is a nuisance the seller can end by cancelling,
  and the check exists to stop a financier being sandwiched into buying a position that earns
  nothing. The trade was taken deliberately.
- v4 permissioned pools: the `UNWIND_WITH_FALLBACK`, `SUBSCRIBE` and `UNSUBSCRIBE` actions are never
  used. A hook refusing transfers to a contract would block listing, which is the behaviour we want.

## 9. Roadmap

1. Done. Build, 34 unit tests including a stateful fuzz over random action sequences (39 with the
   five below, which pass as no-ops off the chain).
2. Done. 5 integration tests forked against live Robinhood Chain state and the real PositionManager:
   custody of the NFT, fee collection without touching liquidity, buyback, delivery to the financier
   of a position they can actually unwind, and the lessee being unable to withdraw liquidity during
   the lease.
3. Front end: listing, funding, the lease timeline, reminders before expiry, rent shown both as an
   amount and as a percentage for the term.
4. Review by a shariah committee on the basis of section 6.
5. Regulatory opinion on section 7 before allowlisting any full-rights tokenised equity pair.
6. An independent audit.
