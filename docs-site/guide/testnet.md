# Testnet

Robinhood Chain testnet (chain id **46630**) is where the whole deal can be run end to end with
nothing at stake: list a position, fund it, collect the fees, buy it back, or let the grace window
run out and take delivery.

<span class="pill live">live</span> The vault is deployed on testnet:

| | Address |
|---|---|
| `LeaseVault` | [`0x27797a2c3428a92c498ed01f3b1c77f636990f7c`](https://explorer.testnet.chain.robinhood.com/address/0x27797a2c3428a92c498ed01f3b1c77f636990f7c) |
| `TestUSDG` (tUSDG) | [`0x182794fbdc0db20341cd61d4d856b0d5101221a4`](https://explorer.testnet.chain.robinhood.com/address/0x182794fbdc0db20341cd61d4d856b0d5101221a4) |
| `TestPositionFaucet` | [`0x901a27604cff123bfae0b4290c287ab50463cbc6`](https://explorer.testnet.chain.robinhood.com/address/0x901a27604cff123bfae0b4290c287ab50463cbc6) |
| `TestToken` (tETH) | [`0x4d3867fbeed7a66462f0e952defd291705f2e4b1`](https://explorer.testnet.chain.robinhood.com/address/0x4d3867fbeed7a66462f0e952defd291705f2e4b1) |

The vault is the same contract that is meant for mainnet, with the same bounds and the same absence of an
owner. Only the settlement token differs.

## What is different from mainnet

| | Mainnet, 4663 | Testnet, 46630 |
|---|---|---|
| Uniswap v4 contracts | canonical addresses | **the same addresses**, verified before deploying |
| Settlement token | USDG | **tUSDG**, a test token anyone can mint |
| Valuation API | yes | no, so you write the terms yourself |
| `LeaseVault` | not deployed | **live**, `0x2779…0f7c` |

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
3. **Get a position.** Press **Get a test position**, on the first screen or on **You**. One
   transaction, and a live Uniswap v4 position lands in your wallet, in range and ready to offer.
4. **Get tUSDG** from the **You** screen, to fund a deal or to buy one back.
5. **Run a deal.** List from one account, fund from another (the vault refuses a seller funding
   their own deal), then collect fees, claim rent, buy back or wait out the grace window.

### Where the test positions come from

Nobody provides liquidity on a network where nothing is worth anything, so a tester would have no
position to lease. The **test position faucet** is that liquidity provider. It owns one pool, tETH
against tUSDG, both test tokens anyone can mint, and every call to `give()`:

- mints both tokens to itself and opens a position six percent either side of the current price,
  sent straight to the caller;
- then trades through the pool, a round trip that ends roughly where it started, so every position
  in range, leased ones included, earns real swap fees. Without it, **Collect the fees** would
  always collect zero.

It has no owner, holds nothing of value, and its constructor refuses mainnet. The source is in
[`lease-vault/src/testnet`](https://github.com/TenureLP/tenure/tree/main/lease-vault/src/testnet),
and a fork test runs a whole deal through it against the deployed vault.

## Quests

Seven things to do with the vault, in the order a deal meets them:

| | Quest | Counted from |
|---|---|---|
| 1 | **Offer a position** | `Listed`, as the seller |
| 2 | **Fund an offer** | `Funded`, as the financier |
| 3 | **Collect the fees** | `FeesCollected`, as the lessee |
| 4 | **Claim the rent** | `RentClaimed`, as the financier |
| 5 | **Buy it back** | `BoughtBack`, on a deal you sold |
| 6 | **Sell your side** | `FinancierTransferred`, as the one handing it on |
| 7 | **Take delivery** | `Released`, on a deal you were financing |

Every one is read from an event the vault emits, the moment it is mined. Nothing is self-reported
and nothing is stored anywhere else: the **Quests** screen of the app reads the vault's events and
counts, address by address, and anyone can do the same count with `cast logs`.

The whole cycle needs two addresses, because a seller cannot fund their own deal, and two days,
because that is the shortest term plus the shortest grace window.

### Founding testers

Every address that completes all seven is listed here, as a founding tester, with the date it
finished. The list is taken from the chain, not from a form.

*No address has completed all seven yet.*

## Found a bug?

The testnet exists so that anything wrong is found before it matters. How to report depends on
what it is:

| If it is… | For example | Report it |
|---|---|---|
| **A way to lose or lock funds**, or to get around one of the vault's bounds | a buyback that pays out twice, a lease that cannot be bought back, a listing the vault should refuse | **Privately**, through [GitHub's private vulnerability reporting](https://github.com/TenureLP/tenure/security/advisories/new). Not in a public issue. |
| **A deal that settles wrongly** | rent credited to the wrong side, a refund that does not add up | Privately, the same way |
| **A figure in the app that could mislead a signature** | a buyback price shown differently from what the wallet is asked to sign | A [public issue](https://github.com/TenureLP/tenure/issues) |
| **Anything else** | a screen that breaks on a phone, wording that is wrong | A [public issue](https://github.com/TenureLP/tenure/issues) |

A good report says which deal or transaction, what you expected, and what happened instead. On the
testnet everything is public and worth nothing, so a report can show every step.

## Shorter terms to test with

The contract's bounds are the same on every chain: a term of at least one day and a grace window of
at least 24 hours. So the shortest complete deal, from funding to `release`, takes two days. A
buyback can be tested immediately after funding.
