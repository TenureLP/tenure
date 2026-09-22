# FAQ

### Is this a loan?

No. Nothing is lent and nothing is borrowed. The seller sells a position, leases it back for a fixed
rent, and holds a promise from the buyer to sell it back at a price agreed upfront. There is no debt,
so there is no interest rate, no health factor, and nothing to liquidate.

### What happens if the price of the pool moves?

Nothing happens to the deal. No oracle is read and nothing is liquidated. The price only matters to the
two parties' decisions: the lessee chooses whether buying back is worth it, and the financier bears the
risk of owning the position if they do not.

### Can I lose my position?

Only by not buying it back before the grace window closes. Until then it is yours to buy back at the
price you agreed, whatever it is worth by then.

### Do I keep the fees?

Yes, for the whole term, as often as you collect them. Collecting is the only thing that can be done to
the position during the lease: its liquidity cannot be withdrawn by anyone.

### Why can the buyback not be higher than the sale price?

Because that difference would be a payment for time, not for the use of anything, which is a loan
with interest under another name. The financier's return is the rent. See
[the buyback rule](/concepts/buyback).

### Does Tenure take a fee?

No. The vault has no fee and no address it pays. A front end may ask to be paid through a
[builder code](/guide/builders), and only the party who names it pays it, capped at 1% of the price.

### Who controls the contract?

Nobody. It has no owner, no admin, no pause and no upgrade path. Every bound on a deal is a constant in
the code.

### Which pools can be listed?

Any Uniswap v4 position that holds liquidity, is in range and has no subscriber. The vault does not
judge pools. Whoever funds a deal decides whether the pool is one they want to own a piece of.

### Is it audited?

Not yet. It is covered by tests, a stateful fuzz, integration tests against the real Uniswap v4
contracts and three adversarial reviews, but no independent audit. It will not be deployed on mainnet
without one.

### Where is the code?

[github.com/TenureLP/tenure](https://github.com/TenureLP/tenure). The contracts carry an MIT licence header.
