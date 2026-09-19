# The token

## What is live

**TEN**, at [`0xD66C5B89fF7b95ad6E73a0B183d74579EB9d6cCb`](https://robinhoodchain.blockscout.com/address/0xD66C5B89fF7b95ad6E73a0B183d74579EB9d6cCb)
on Robinhood Chain. One billion units, eighteen decimals, launched on the Pons bonding curve.

It was **created by the Pons launchpad from its own template**, not from `TenureToken.sol` in this
repository. That file is a reference and a test, and it is not what is deployed. Saying so matters
more than the tidiness of pretending otherwise.

What was checked against the deployed contract, and what anybody can check again:

```bash
cd lease-vault && ./check-token.sh
```

It asks the contract for twenty-four selectors — ownership, minting, pausing, blacklisting, taxing,
trading gates, upgrading — and reports which it answers. **It answers none of them.** The script
defaults to the public RPC, so repeating it needs no key and no trust in this file.

### There was an earlier contract

TEN was deployed twice. The first contract, at `0x4bA94fB1D3fDF414afdc955CD29836016eDF3531`, was
abandoned and replaced by the one above. It is not hidden here because somebody will find it, and a
project that only mentions the contract it likes is the one people stop believing.

At the time of the change the curve still held 97.3% of that supply, and two ordinary accounts held
the rest: one with 2.34%, one with a rounding error. Whoever that first holder is, the token they
bought is no longer the one being talked about. If they are not us, they should be made whole, and
this file should say how they were.

Also read from the chain: the deploying address holds **zero** TEN on both contracts. There was no
developer buy in either launch transaction, which is the thing to look at first on any bonding-curve
launch and the thing a screenshot of a website cannot tell you.

## What follows

Everything below describes `TenureToken.sol`, the contract in this repository. The live token is not
that contract, but it was held to the same test, which is the only reason its properties can be
stated here at all.


`TenureToken` is a fixed-supply ERC-20 with no owner, no minter, no pause, no blacklist, no fee on
transfer and no upgrade path. The whole supply exists after the constructor and can only fall,
because holders may burn their own balance. That is the entire contract, and the emptiness is the
design: a token is the one place in a system where a hidden power is worth most to whoever holds it
and costs most to everyone else.

## What it does not do

**It has no utility today.** No revenue reaches it. No vote is counted with it. Holding it entitles
you to nothing, and nothing in the contract suggests otherwise.

Anyone who tells you it will is speaking for themselves. When that changes it will change here, in
this file, pointing at a deployed contract anybody can read — not in a post.

**The protocol it is named after takes no fee.** `LeaseVault` charges nothing and pays no address of
its own; that is [deliberate and permanent](../lease-vault/docs/SPEC.md). So there is no protocol
revenue to share, and a token cannot be given a claim on money that is never collected.

## What could give it one

There is exactly one place in the architecture where money is earned for a service rendered, and it
is not the vault. It is the **builder code**.

Each side of a deal may name a builder and pay them a flat amount for bringing them the deal: the
seller out of their proceeds, the financier on top of the price. Zero by default, capped at a
hundredth of the price, and it never touches the vault. Whoever runs a front end that brings deals
together can be named there.

If that front end names a **contract** as its builder rather than a wallet, the fees it earns arrive
somewhere with rules instead of somewhere with a private key. That contract could buy the token back
and burn it, on a schedule nobody controls, from revenue that exists because a real service was
performed.

That is the honest shape, and it is worth saying why it is the right one here rather than a coupon
on somebody else's money: it is a share in the profits of a service, not a claim on a loan. The rest
of this project exists to avoid the second thing.

**None of that is built.** There is no treasury contract, no buyback, no front end earning builder
fees. Until there is, the paragraph above is a plan and the one before it is the truth.

## Supply and where it goes

The constructor mints the whole supply to one address and there is no second mint. Which address,
and what it does next, is a disclosure rather than a property of the contract — the code cannot make
anyone honest about distribution, so it does not pretend to.

What should be published before anyone is asked to buy, and what this file will carry when it is:

1. the recipient of the initial mint, and what it did with the supply;
2. every allocation that is not in circulation, with the beneficiary category;
3. for each locked allocation, the cliff, the duration, the release schedule and the on-chain
   vesting address;
4. whether any of it can be revoked or changed, and by whom.

An allocation that cannot be pointed at on chain should be read as one that does not exist yet, or
as one somebody would rather you did not look at.

## Risk, plainly

A fixed supply is not a floor. The contract cannot create demand, and nothing here promises any. The
price of a token with no utility is whatever the next person will pay, which is a sentence that has
ended badly for a great many people.

Nothing in this repository is audited. No contract is deployed on any chain. If you are reading this
because somebody sent you a link and told you to buy, that person is not us and you should be
suspicious of them.
