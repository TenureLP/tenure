# Testnet

Robinhood Chain testnet (chain id **46630**) is where the whole deal can be run end to end with
nothing at stake: list a position, fund it, collect the fees, buy it back, or let the grace window
run out and take delivery.

<span class="pill soon">deploying</span> The vault is being deployed to testnet. This page will
carry its address the moment it is live.

## What is different from mainnet

| | Mainnet, 4663 | Testnet, 46630 |
|---|---|---|
| Uniswap v4 contracts | canonical addresses | **the same addresses**, verified before deploying |
| Settlement token | USDG | **tUSDG**, a test token anyone can mint |
| Valuation API | yes | no, so you write the terms yourself |
| `LeaseVault` | not deployed | deploying |

### tUSDG

The testnet has no USDG, so the deploy creates `TestUSDG`: six decimals like the real token, named
**Test USDG (worthless)**, and mintable by anyone, without limit, with `mint(address to, uint256 value)`.

That last property is deliberate. A test token that could be scarce is a test token somebody will
eventually try to sell. This one is worth exactly nothing, by construction.

### No valuation, so you write the terms

<figure class="shot">
  <div class="bar"><i></i><i></i><i></i></div>
  <img src="/shots/testnet.jpg" alt="The app in testnet mode" loading="lazy">
  <figcaption>On testnet the first screen is Offer: paste a position, the chain confirms who holds it, you write the terms.</figcaption>
</figure>


The valuation API prices a position in USDG by reading USDG pools, and the testnet has none. On
testnet the app's first screen is **Offer** instead of **Value**: you paste a position id, the app
confirms from the chain who holds it, and you write the price, buyback and rent yourself.

That is not a weaker mode. The vault is what checks a listing, and the app dry-runs every
transaction with `eth_call` before your wallet is asked, so a listing the vault would refuse comes
back with its reason (`BuybackAboveSale`, `OutOfRange`, `BadTerm`…) before any gas is spent.

## Trying it

1. **Get testnet ETH** for gas from the Robinhood Chain testnet faucet. A deal costs a few hundred
   thousand gas at most, which on testnet is a fraction of a cent.
2. **Open the app on testnet:**
   [app-production-7810.up.railway.app/?chain=46630](https://app-production-7810.up.railway.app/?chain=46630).
   Connect your wallet; if it is on another chain, the app offers to switch.
3. **Have a position.** Any Uniswap v4 position on testnet that holds liquidity, is in range and has
   no subscriber can be listed.
4. **Get tUSDG** from the **You** screen, to fund a deal or to buy one back.
5. **Run a deal.** List from one account, fund from another (the vault refuses a seller funding
   their own deal), then collect fees, claim rent, buy back or wait out the grace window.

::: tip Break it
The testnet exists so that anything wrong is found before it matters. If the app lets you do
something it should not, or refuses something it should allow, that is exactly what we want to hear
about: open an issue on [GitHub](https://github.com/TenureLP/tenure/issues).
:::

## Shorter terms to test with

The contract's bounds are the same on every chain: a term of at least one day and a grace window of
at least 24 hours. So the shortest complete deal, from funding to `release`, takes two days. A
buyback can be tested immediately after funding.
