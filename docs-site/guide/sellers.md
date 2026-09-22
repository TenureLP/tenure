# Selling a position

You hold a Uniswap v4 position and want cash now, without closing it and without giving up what it
earns. You sell it to a financier, lease it back, and keep collecting its fees until you buy it back.

## What you need

- A Uniswap v4 position NFT on Robinhood Chain that:
  - **holds liquidity.** An empty position has nothing to lease.
  - **is in range.** Out of range it earns nothing, so there is nothing to lease or to buy. This is
    checked when you list and again when somebody funds.
  - **has no subscriber.** A position with a subscriber attached cannot be listed.
- Some ETH for gas.

## Choosing the terms

<figure class="shot">
  <div class="bar"><i></i><i></i><i></i></div>
  <img src="/shots/value-position.jpg" alt="Position 3093793 valued" loading="lazy">
  <figcaption>What the position holds, and what its range really earned over a day of chain history.</figcaption>
</figure>


The app proposes terms from the valuation API: a sale price at a discount to market value, a buyback
equal to the sale price, and a rent sized from what the range actually earned over the last day. Every
field is yours to change.

**Price.** What the financier pays you. You receive it immediately, minus the rent and minus any
builder fee you agreed to pay.

**Rent.** A fixed amount for the whole term, prepaid out of your proceeds. You are refunded whatever
has not accrued if you buy back early. It is never a percentage, never compounds, and never grows.

**Buyback price.** What you pay to get the position back. The vault refuses any buyback above the
sale price. Most listings set it equal to the price.

**Term and grace.** The lease runs for the term (1 to 30 days). After it, you have the grace window
(24 hours to 7 days) to buy back. Fees can be collected during the term only.

::: tip Pricing the rent
The fees the position earns over the term are yours, and the rent is what you pay for having the cash
meanwhile. A rent below the fees you expect to collect means the lease pays for itself. The app shows
the rent as a share of the price, per term and per year, so you can compare it with borrowing.
:::

## Listing

<figure class="shot">
  <div class="bar"><i></i><i></i><i></i></div>
  <img src="/shots/value-terms.jpg" alt="Indicative terms and the listing form" loading="lazy">
  <figcaption>The Value screen proposes terms from the valuation; every field is yours to change.</figcaption>
</figure>


In the app, open **Value** (or **Offer** on testnet), paste your position id, check the terms and
click **List this position**. Two transactions:

1. **Step 1 of 2** approves the vault to take the NFT,
2. **Step 2 of 2** lists it.

Each is dry-run first, so a refusal shows its reason before your wallet opens. Once listed, the
position sits in the vault until a financier funds it, the offer expires, or you **cancel** it.

## During the lease

<figure class="shot">
  <div class="bar"><i></i><i></i><i></i></div>
  <img src="/shots/lessee.jpg" alt="The lessee's view of an active deal" loading="lazy">
  <figcaption>Your proceeds, the fees to collect, and the buyback, all on the You screen.</figcaption>
</figure>


Your proceeds are in the vault as a balance: withdraw them from the **You** screen whenever you like.

Click **Collect the fees** as often as you want. The fees go straight to your wallet. The liquidity is
untouchable, by you or by anybody else, for the whole lease.

## Buying back

Any time until the grace window closes, **Buy it back** pays the buyback price and returns the position
to you. The rent that had not accrued yet is refunded to your balance, then you withdraw the position.

If the vault is holding money for you (your proceeds, for instance), withdraw it first: buying back
pays from your wallet.

## If you do not buy back

After the grace window, the financier can take delivery. They keep the position and the full rent.
You keep the sale price you were paid and every fee you collected during the lease. Nothing else
happens: no debt remains, and nothing further can be claimed from you.
