---
layout: home

hero:
  name: Tenure
  text: Your liquidity position, without giving it up.
  tagline: Sell a Uniswap v4 position for cash, lease it straight back, keep every fee it earns, and buy it back at a price fixed before any of it starts.
  image:
    src: /logo-512.png
    alt: Tenure
  actions:
    - theme: brand
      text: How a deal works
      link: /guide/how-a-deal-works
    - theme: alt
      text: Open the app
      link: https://app-production-7810.up.railway.app
    - theme: alt
      text: Testnet
      link: /guide/testnet

features:
  - icon: { src: /icons/coins.svg }
    title: No loan
    details: Nothing is lent. The position is sold, then leased back. There is no debt, so there is no interest rate and no health factor.
  - icon: { src: /icons/shield.svg }
    title: No liquidation
    details: Nothing can be seized. If the lessee never buys back, the financier simply keeps what they already own.
  - icon: { src: /icons/no-oracle.svg }
    title: No oracle
    details: The deal path reads no price feed. Every figure is agreed upfront by the two parties and enforced by the contract.
  - icon: { src: /icons/chart.svg }
    title: Keep the fees
    details: For the whole lease, the lessee collects the swap fees the position earns, as often as they like. The liquidity itself cannot be touched.
  - icon: { src: /icons/ceiling.svg }
    title: A buyback that cannot grow
    details: The buyback price can never exceed the sale price. The financier is paid rent for the use of the asset, never for the passage of time.
  - icon: { src: /icons/no-owner.svg }
    title: A primitive, not a platform
    details: The vault has no owner, no fee, no pause, no upgrade path and no allowlist. Once deployed, nobody can change what it does.
---

## The app, as it runs

<div class="gallery">
  <a href="/guide/sellers"><img src="/shots/value-position.jpg" alt="Valuing position 3093793" loading="lazy"><span><b>Value</b> what it holds and earns</span></a>
  <a href="/guide/financiers"><img src="/shots/market.jpg" alt="A listing on the market" loading="lazy"><span><b>Market</b> somebody funds it</span></a>
  <a href="/guide/sellers#during-the-lease"><img src="/shots/lessee.jpg" alt="The lessee's view of an active deal" loading="lazy"><span><b>You</b> keep the fees, buy it back</span></a>
</div>

Real screens, from the app running against a fork of Robinhood Chain with the real USDG and the real
Uniswap v4 contracts. [See every screen](/app/).

## In one paragraph

A liquidity provider lists a Uniswap v4 position on the vault with a price, a rent, a buyback price
and a term. A financier funds it: they pay the price and become the owner of the position. The seller
receives the price minus the prepaid rent, and immediately leases the position back. For the length
of the lease the seller, now the lessee, keeps collecting the pool's swap fees. At any point before
the grace window closes they can buy the position back at the price agreed on day one, and any rent
that has not accrued yet is refunded. If they do not, the financier takes delivery of the position
they already own.

## Where things stand

| Piece | State |
|---|---|
| The [app](https://app-production-7810.up.railway.app) | <span class="pill live">live</span> values any position on Robinhood Chain today |
| The [valuation API](/api/) | <span class="pill live">live</span> reads mainnet, exact integer maths |
| On [Olanas](/api/agents) | <span class="pill live">live</span> agents buy a valuation for 0.003 USDG a call |
| `LeaseVault` on Robinhood Chain testnet | <span class="pill live">live</span> the whole deal, with a test token anyone can mint: see [Testnet](/guide/testnet) |
| `LeaseVault` on Robinhood Chain mainnet | <span class="pill no">not deployed</span> no audit yet, and none will go live without one |

::: warning Prototype
Nothing here is audited. The contracts have been reviewed adversarially and are covered by tests,
including a stateful fuzz and integration tests against the live Uniswap v4 contracts, but an
independent audit has not happened. See [what is guaranteed, and what is not](/concepts/guarantees).
:::
