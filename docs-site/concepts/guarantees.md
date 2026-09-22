# What is guaranteed, and what is not

## Enforced by the contract

These hold for every deal, and cannot be changed by anyone, because the vault has no owner and no
upgrade path:

- **The vault never owes more USDG than it holds.**
- **Rent paid out never exceeds the rent escrowed** at funding.
- **Frozen time never exceeds its ceiling**, at most half the term.
- **A position is owed to at most one party** at any time.
- **The lessee can collect fees but can never withdraw liquidity**, and neither can anyone else,
  during the lease.
- **The buyback price never exceeds the sale price.**
- **The seller can never fund their own deal**, and a financier cannot sell their side to the seller.
- **A financier who takes delivery receives a position they can actually unwind.**
- **Every payout is pulled**, never pushed, so no recipient can block somebody else's deal.

Each of these is checked by tests, including a stateful fuzz that runs random sequences of every
action and checks the invariants after each one, and by integration tests against the real Uniswap
v4 PositionManager on Robinhood Chain.

## What the vault does not do

- **It has no owner.** No pause, no upgrade, no parameter anyone can change.
- **It takes no fee.** There is no address anywhere that the vault pays. [Builder codes](/guide/builders)
  are paid by the party that names them, out of their own money.
- **It has no allowlist.** Any pool that can be settled can be listed. Whether a pool is worth
  funding is the financier's decision, not the contract's.
- **It reads no oracle.** Every figure is agreed by the parties upfront.

## Not established

::: danger Read this before putting money in
- **No independent audit.** Three adversarial reviews have been run and their findings fixed, but no
  audit firm has reviewed the code.
- **No mainnet deployment.** The vault is not deployed on mainnet and will not be without an audit.
- **No economic review** of lease terms under stress.
- **No formal verification.**
- **The valuation API is a model.** Its quotes are a starting point for negotiation, computed from the
  pool's own price and one day of fee history. A manipulated pool is not detected.
:::

## Risks that stay with the parties

**For the financier:** the position can lose value, drift out of range, or sit in a pair whose
tokens can be frozen. If the lessee does not buy back, the financier owns whatever the position is
worth then.

**For the lessee:** missing the grace window means the position is gone for good. The vault will
not extend it.

**For both:** the tokens in the pool, and USDG itself, are contracts written by others, with their own
risks.
