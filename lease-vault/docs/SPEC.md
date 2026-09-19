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
| Registry | Admission policy, owner-managed | The pool allowlist, terms, grace window, a capped flat fee |
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
| Flat protocol fee | 2 USDG |
| Received by the seller at funding | 1,804 USDG |

The financier earns 9 USDG of rent if the lease runs its course, about 0.5% over 7 days, plus 1,815
at the buyback. If there is no buyback they keep a position worth whatever it is worth. The seller
paid 2 USDG of fees and 9 USDG of rent for 1,815 USDG of cash, while collecting the week's swap fees.

Enforced in code: rent plus fee must be below the price, and neither the rent nor the buyback price
may be zero. The buyback price is otherwise free. The interface suggests a sale price near market
value; the discount is negotiated, not imposed.

## 5. Rent, and freezes of the underlying

Rent is a fixed amount for the term, prepaid into escrow, streaming linearly per usable second. It
never compounds and the contract never annualises it.

The lessor carries an owner's risk. In v1 that risk is expressed through freezes: on every
interaction and on every `checkpointFreeze`, the vault asks each token of the pair whether it is
paused, using the probe the registry recorded for that pool. Frozen seconds are removed from the rent
base and refunded to the lessee at settlement. The calendar term itself does not stretch.

Two bounds sit on that, and the second one is a policy choice the committee owns.

A freeze counts for at most `MAX_FREEZE_GAP` (6 hours) beyond the last time it was actually
observed, so nobody can open one and let it run unattended.

On top of that, a deal may credit at most `maxFrozenBps` of its term as frozen, 25% by default.
Sampling cannot distinguish "frozen all week, observed every six hours" from "halted for one second
at each of those instants", so without a total ceiling a lessee who checkpoints during repeated
brief halts could wipe out the rent for a few dozen cheap transactions. The ceiling is what makes
the financier's downside something they can read and price before they fund.

The cost of that ceiling is real and points the other way: a pair that genuinely halts for longer
than the ceiling makes the lessee pay rent for time the asset was unusable. For the v1 allowlist,
crypto pairs that never halt, 25% is slack. Tokenised equities halt every night and every weekend,
which is well past it, so allowlisting such a pair means raising `maxFrozenBps` and accepting the
sampling exposure that comes with it, or redesigning the freeze evidence entirely.

Known limit: a position destroyed by an exploit in the pool is not detectable generically on chain.
In that case the financier owns a worthless position and the lessee owes nothing more, which is the
expected outcome for a lease.

## 6. How the design maps to the fiqh requirements

| Requirement | Mechanism in the code | Reference |
|---|---|---|
| A real sale, with ownership transferred | The NFT is recorded to the financier at `fund`, transferable via `transferFinancierPosition`, delivered by `release` with no "claim" step | AAOIFI 9, 3/1; 2008 sukuk statement |
| The lessor carries the asset risk | Rent suspended while frozen, the unaccrued part refunded; no claim on the lessee if the asset is destroyed | AAOIFI 9, 5/1/7 |
| Rent for a real usufruct | The lessee collects the swap fees through `collectFees`; the position must be in range at listing and at funding, and above a minimum liquidity | AAOIFI 9, 5/1 |
| No 'inah | Sale and lease are two acts settled in order inside `fund`; the financier cannot transfer to the lessee except through `buyBack`. The `SelfDeal` check compares addresses: it stops the obvious self-funding, not a seller using a second address. No on-chain check can do better, and the committee should weigh that | OIC Fiqh Academy, res. 66; AAOIFI 9, 3/2 |
| Buyback by unilateral promise, at a price fixed in advance | `buyBack` at `buybackPrice`, exercised at the lessee's sole discretion | AAOIFI 2008 statement on ijarah sukuk, provided the lessor bears total loss |
| No ghalaq ar-rahn | There is no pledge: the financier keeps nothing, they take delivery of what is theirs | Hadith "la yughlaq ar-rahn" |
| A service fee at cost, not a percentage | `listingFee` is a flat amount, capped when the registry is deployed, snapshotted into the deal | AAOIFI 19 on qard fees, by analogy |
| No oracle, no liquidation | No price is read in the deal path; `StateView` only checks the range at listing and at funding | Product principle |
| Permissible assets | Allowlist per pool, with `assetClass` and `screeningRef` | AAOIFI 21 screening for equities |

Open points for a committee to settle:

1. Rent shown by the interface as a percentage of the price, even though the contract only knows an
   amount. AAOIFI allows rent to be indexed; presentation does not change the nature of the contract.
2. A buyback at a fixed price equal to the sale price. Allowed by the 2008 AAOIFI statement for
   ijarah sukuk, criticised by some scholars. The alternative, a buyback at market value computed
   from pool state, exposes the deal to price manipulation in shallow pools.
3. Refunding unaccrued rent on an early buyback. Consistent with a lease that ends when ownership
   transfers; some committees prefer the buyback price plus the remaining rent.
4. Whether an LP position on a crypto pair counts as productive. Swap fees are payment for a market
   service; permissibility depends on both tokens and on the pool containing no lending mechanism.

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
