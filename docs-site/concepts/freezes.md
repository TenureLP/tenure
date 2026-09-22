# Freezes

Some tokens can be paused by their issuer. USDG, for instance, sits behind an upgradeable proxy and
exposes `paused()`. While a token in the pair is frozen, the position cannot really be used, so the
lease should not charge for that time.

## The probe

The seller picks how the vault asks whether the pair is frozen, in the terms:

| `freezeProbe` | Behaviour |
|---|---|
| `0` | never asks. Rent accrues for every second of the term |
| `1` | calls `paused()` on both tokens of the pair |

The call is made with a fixed gas allowance and reads at most one word back, so a hostile token
cannot make it expensive. A token with no `paused()` function counts as not frozen. A token that
answers in an unexpected shape counts as frozen.

## Recording a freeze

The vault cannot watch the chain. A freeze is recorded when somebody touches the deal: any
state-changing call checkpoints it, and anyone can call `checkpointFreeze(dealId)` directly.

Both sides have a reason to: the lessee to open a freeze and stop the rent, the financier to close
one and restart it.

## Two limits, both protecting the financier

**No drifting.** An open freeze only counts up to **6 hours** (`MAX_FREEZE_GAP`) past the last time it
was actually observed. Somebody who opens a freeze during a one-second halt and never closes it
gains at most six hours, not the rest of the term.

**A ceiling for the whole deal.** Total frozen time credited can never exceed `maxFrozenBps` of the
term, and `maxFrozenBps` can never exceed **5000**, half the term. Sampling cannot tell "frozen all
week" from "halted for a second each time somebody looked", so the ceiling is what lets a financier
know their worst case when they fund.

## What a financier should check

A deal with `freezeProbe = 1` and a high `maxFrozenBps` on a pair with a pausable token can refund a
large share of its rent. The app shows both under **Builder code and freeze handling** when listing,
and the vault's constants cap how far it can go.
