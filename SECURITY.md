# Security

Tenure is a prototype. Nothing in this repository has been independently audited, and no contract
is deployed on mainnet. The vault runs on Robinhood Chain testnet so that anything wrong with it is
found while nothing is at stake.

## Reporting a vulnerability

**Please report privately**, through GitHub's private vulnerability reporting:

**[Report a vulnerability](https://github.com/TenureLP/tenure/security/advisories/new)**

That opens a draft advisory only the maintainers can see. Please do not open a public issue for
anything that could lose or lock funds, or get around one of the vault's bounds.

A useful report names the contract and function, the deal or transaction if there is one, what you
expected, and what happened. On the testnet everything is public and worthless, so a report can
show every step of a reproduction.

## In scope

- `lease-vault/src/LeaseVault.sol`, deployed on Robinhood Chain testnet at
  `0x27797a2c3428a92c498ed01f3b1c77f636990f7c`
- the app, where what it shows could mislead somebody about what they are signing
- the valuation API, where a figure it returns is wrong

Test tokens and the test position faucet are worthless by construction. A way to mint them is not
a vulnerability: anyone can already.

## Everything else

A screen that breaks, wording that is wrong, a figure that is off without misleading a signature:
a [public issue](https://github.com/TenureLP/tenure/issues) is the right place.
