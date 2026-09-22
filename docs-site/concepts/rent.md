# Rent and how it accrues

Rent is a **fixed amount for the whole term**, agreed when the deal is listed. It is not a rate, it does
not compound, and nothing can make it grow.

## Prepaid, then streamed

At funding, the rent is deducted from the seller's proceeds and held by the vault. From then on it
accrues to the financier **per usable second** of the term:

```
accrued = rent × usable seconds ÷ term
usable  = elapsed − frozen          (never below zero)
elapsed = now − fundedAt            (clamped to the end of the term)
```

Accrual stops at the end of the term. The grace window earns no rent.

## Claiming

`claimRent(dealId)` credits the financier's balance with whatever has accrued and not been claimed
yet. Anyone can call it, and the money always goes to the current financier. It reverts with
`NothingOwed` when there is nothing new.

Rent is also settled automatically:

- when the financier sells their side, to the outgoing financier,
- on `buyBack` and on `release`, to the financier.

## Refunds

Whatever has not accrued when the deal ends goes back to the lessee:

- **Early buyback.** Buy back on day 3 of a 7-day lease and roughly four sevenths of the rent come
  back to you.
- **Frozen time.** Seconds during which the pair was frozen are not usable, so they earn no rent and
  are refunded, up to the [ceiling](/concepts/freezes) set in the terms.

## Reading it

| View | Returns |
|---|---|
| `accruedRent(dealId)` | rent accrued so far, net of recorded frozen time |
| `leaseEnd(dealId)` | `fundedAt + term`, or the far future if not funded |
| `graceEnd(dealId)` | `fundedAt + term + grace`, or the far future if not funded |

`leaseEnd` and `graceEnd` return the far future, not zero, for an unfunded deal: the question callers
ask is `now >= graceEnd(id)`, and zero would answer yes.

## The figure the app shows

Every deal card shows **rent on price**, the rent as a percentage of the sale price over the term,
and the same figure scaled to a year. It is there to compare one listing with another, and with
borrowing. It is not a rate the contract applies: the contract only knows the fixed amount.
