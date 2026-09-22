# How a deal works

Every deal has two parties and one contract. The **seller** owns a Uniswap v4 position and wants
cash. The **financier** has cash and wants a return. `LeaseVault` holds the position and the money in
between, and enforces the terms both of them agreed to.

```
        SELLER                        VAULT                       FINANCIER
          │                             │                              │
          │ list(terms)                 │                              │
          ├────────── NFT ─────────────▶│                              │
          │                             │◀───────── fund() ────────────┤
          │◀─ price − rent − fee ───────┤  ownership recorded          │
          │                             │  rent escrowed               │
          │                             │                              │
          │    ┌────────────────────────┴───────────────────┐          │
          │    │  the lease: 1 to 30 days                   │          │
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

## 1. Listing

The seller approves the vault for their position NFT and calls `list` with the terms. The NFT moves
into the vault, and the deal is **Listed**.

| Term | What it is | Bounds |
|---|---|---|
| `price` | What the financier pays for the position | more than zero |
| `rent` | Total rent for the whole term, deducted from the proceeds | more than zero, and `rent + builderFee < price` |
| `buybackPrice` | What the seller pays to get the position back | more than zero, **never above `price`** |
| `term` | Length of the lease | 1 to 30 days |
| `grace` | Extra time to buy back after the term ends | 24 hours to 7 days |
| `listingDuration` | How long the offer stays open | up to 30 days |
| `maxFrozenBps` | Most of the term that can be credited as frozen | up to 5000 (half the term) |
| `freezeProbe` | `0` never checks the pair for a freeze, `1` calls `paused()` on both tokens | 0 or 1 |
| `builder`, `builderFee` | Who brought the seller here, and what they are paid | at most 1% of the price |

The vault only checks that it can settle the deal: the position has liquidity, is in range, and
has no subscriber attached. It does not judge the pool. That is the financier's call.

While a deal is Listed, the seller can `cancel` it and withdraw their position.

## 2. Funding

<figure class="shot">
  <div class="bar"><i></i><i></i><i></i></div>
  <img src="/shots/deal-card.jpg" alt="A listed deal" loading="lazy">
  <figcaption>A listed deal, as a financier sees it on the market.</figcaption>
</figure>


A financier calls `fund`. They pay the price in USDG, and the vault:

- records them as the **owner** of the position,
- credits the seller with `price − rent − builderFee`,
- keeps the `rent` in escrow,
- starts the lease clock. The deal is now **Active**.

The position is checked to still be in range at this moment too: a listing stays open for days, and a
position that drifted out of range earns nothing to lease.

## 3. The lease

For the whole term:

- the **lessee** (the seller) calls `collectFees` whenever they like and receives the swap fees the
  position earns. That call is built so it can only ever collect: it decreases liquidity by zero.
  Liquidity cannot be withdrawn by anyone during the lease.
- the **rent** streams to the financier second by second. Anyone can call `claimRent` to credit what
  has accrued so far.
- the **financier** can sell their side with `transferFinancierPosition`. The lease carries on
  unchanged for the lessee: same rent, same buyback price, same dates.

## 4. The end

Two ways out, and nothing in between.

**The lessee buys back.** Any time from funding until the grace window closes, `buyBack` pays the
buyback price. The financier is credited with the buyback price plus any rent not yet claimed, the
lessee is refunded the rent that had not accrued yet, and the position becomes the lessee's again.
The deal is **BoughtBack**.

**The financier takes delivery.** Once the term and the grace window are both over, the financier
calls `release`. The full rent is theirs, and so is the position. The deal is **Released**.

Nobody is liquidated in either case. The financier bought a position; they either sell it back at
the agreed price or they keep it.

## Payouts

The vault never pushes money or NFTs to anyone. Every payout is a balance the owed party withdraws
themselves, with `withdrawUSDG` and `withdrawPosition`. A recipient that cannot receive a transfer
can therefore never block somebody else's deal.

## States

```
None ──list──▶ Listed ──fund──▶ Active ──buyBack──▶ BoughtBack
                 │                 │
               cancel            release (after term + grace)
                 ▼                 ▼
             Cancelled          Released
```
