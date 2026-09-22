# Using the app

[app-production-7810.up.railway.app](https://app-production-7810.up.railway.app) is the deal flow as a
single page: three screens, one wallet button, nothing to install.

## The three screens

**Value** (on testnet, **Offer**). Paste a position id and see what it holds, what its range actually
earned over a day of chain history, and the terms it could be offered on. With a vault deployed, list
it from the same screen.

**Market.** Every open listing, with the pair, the sale price, the buyback, the rent and the rent on
price per term and per year. Fund one from here.

**You.** Every deal you are a party to, on either side, and whatever the vault holds for you: USDG to
withdraw, and positions to withdraw. The actions for each deal sit on its card: collect the fees, buy
it back, claim the rent, sell your side, take delivery.

## Chains

A selector in the header switches between Robinhood Chain and its testnet. Link straight to one with
`?chain=4663` or `?chain=46630`. If your wallet is on the wrong chain, a **Switch** button appears in
the header, and that is the only time it does.

## What the page does before your wallet opens

- **Every transaction is dry-run** with `eth_call`. A refusal comes back named, before any gas is spent.
- **Approvals are exact.** Funding approves the price, buying back approves the buyback price, never an
  unlimited allowance.
- **Two-step actions say so**: *Step 1 of 2* approves, *Step 2 of 2* acts.
- **Times come from the chain**, not your computer's clock.

## What the page cannot do

- It holds no key and signs nothing itself. Every write goes through your wallet.
- It loads scripts only from its own origin, talks only to the chain RPCs and the valuation API, and
  cannot be framed by another site.

## Linking to a position

`?id=<tokenId>` opens the Value screen on that position:

```
https://app-production-7810.up.railway.app/?id=3093793
```
