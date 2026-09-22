# Funding a deal

You have USDG and want a return on it. You buy a liquidity position at a price the seller set, lease
it back to them for a fixed rent, and either sell it back at an agreed price or keep it.

## What you are buying

When you fund a deal you become the **owner** of the position. That is not a figure of speech: the
vault records you as the owner, you can sell that ownership on, and if the lessee does not buy back,
the position is yours to withdraw.

In return for the lease you receive the **rent**, prepaid by the seller and held in escrow by the
vault. It streams to you second by second over the term.

## What you should look at

The vault checks that a deal can be settled. It does **not** judge whether it is a good one. Before
funding, look at:

- **The pool.** Which two tokens, and whether you are willing to end up holding a position in them.
  If the lessee does not buy back, that is exactly what you get.
- **The price against the value.** The app shows the market value next to the sale price. The
  difference is your margin if you take delivery.
- **The rent on price.** Shown per term and per year on every deal card.
- **The range.** A narrow range can drift out and stop earning. The position must be in range when
  you fund, not for the whole lease.
- **Freeze handling.** See [freezes](/concepts/freezes): if a token in the pair can be paused by its
  issuer, frozen time does not earn rent, up to the ceiling the seller set.

## Funding

<figure class="shot">
  <div class="bar"><i></i><i></i><i></i></div>
  <img src="/shots/market.jpg" alt="A listing on the market" loading="lazy">
  <figcaption>Every open listing, with the pair and the rent on price, per term and per year.</figcaption>
</figure>


In the app, open **Market**, pick a listing and click **Fund it**. Two transactions:

1. **Step 1 of 2** approves exactly the price in USDG (never an unlimited allowance),
2. **Step 2 of 2** funds the deal.

## During the lease

<figure class="shot">
  <div class="bar"><i></i><i></i><i></i></div>
  <img src="/shots/financier.jpg" alt="The financier's view of an active deal" loading="lazy">
  <figcaption>Claim the rent so far, or sell your side. The lessee's terms never change.</figcaption>
</figure>


- **Claim the rent so far** credits the accrued rent to your balance. Anyone may trigger it; it always
  pays you.
- **Sell your side** transfers your ownership to another address. Accrued rent is settled to you
  first; the new owner receives everything from then on. The lessee's terms do not change.
- Withdraw your balance from the **You** screen at any time.

## The end

- **If the lessee buys back**, you are credited the buyback price plus any rent not yet claimed.
- **If they do not**, once the term and the grace window are over, **Take delivery** (`release`)
  credits the remaining rent and makes the position yours to withdraw.

You cannot force an early exit, and the lessee cannot withdraw the liquidity out from under you.
