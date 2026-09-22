# Your positions

The **Positions** screen reads every Uniswap v4 position a wallet holds on Robinhood Chain and says,
for each one, what it holds, what it earns, what its pool's hook is allowed to do, and what can be
done about it. It only reads: nothing is signed, and you can look up any address, not only your own.

<figure class="shot">
  <div class="bar"><i></i><i></i><i></i></div>
  <img src="/shots/positions.jpg" alt="The Positions screen: totals, filters, and a card per position with its range and findings" loading="lazy">
  <figcaption>A wallet with 72 positions. The summary counts them, the filters narrow them, each card carries its range and what can be said about it.</figcaption>
</figure>

## What it shows

**The totals.** How many positions the wallet holds, how many are in range, what they are worth in
USDG, the fees waiting to be collected and what the whole wallet earned over the last day.

**Per position.** The pair, the value, the uncollected fees, the fees per day and the APR over the
last day, and a bar showing where the price sits against the range.

**Findings.** Facts, most pressing first, each with the options it opens. They never tell you what
to do:

| Finding | What it means |
|---|---|
| Out of range | The price has left the range, so the position earns nothing. It says how far the price would have to move to come back. |
| Close to an edge | A small move takes it out of range. It says how small. |
| Fees to collect | Uncollected fees worth taking, against what the position holds. |
| Earning little | In range, but the fees over the window come to little against its size. |
| Pool with a hook | The pool has a hook, and what that hook is allowed to do. |
| A subscriber is attached | Another contract is notified of every change. The vault refuses to lease such a position. |
| Could raise on Tenure | The position is eligible, with the price and rent it could raise. |

## Hooks

In Uniswap v4 a hook's permissions are written into its address: the low 14 bits say which points of
the pool's life it is called at. That is read without asking the chain anything, and it is what the
hook pill on a card reports.

What matters to a holder:

| Permission | Effect |
|---|---|
| `afterRemoveLiquidityReturnDelta` | The hook can take a share of what is withdrawn, fees included. |
| `beforeRemoveLiquidity`, `afterRemoveLiquidity` | The hook runs on every withdrawal and fee collection, and can refuse one. |
| `afterAddLiquidityReturnDelta` | It can take a share of what is added. |
| `beforeSwapReturnDelta`, `afterSwapReturnDelta` | It can change what a swap pays, so fee income need not follow volume. |
| Dynamic fee | The pool's fee is set by the hook and can change at any time. |

A pool whose hook can refuse a withdrawal is one to look at twice before leasing the position: the
lessee's right to collect the fees runs through that hook.

## Where the list comes from

The PositionManager cannot list the tokens an address owns, so the wallet's positions are rebuilt
from the chain's transfer history and then checked one by one for who holds them now. Two
consequences:

- The first look at a wallet takes a few seconds. The service keeps the answer warm afterwards.
- A wallet that has received thousands of positions, which market-making bots do, is read from its
  most recent transfers backwards. The screen says so, and the API answers `complete: false`.

## From an agent

The same answer is one HTTP call, `GET /v1/owner/{address}/positions`: see
[a whole wallet](/api/#a-whole-wallet) and [using it from an agent](/api/agents).
