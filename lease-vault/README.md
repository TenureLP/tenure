# Lease Vault

Sale-and-leaseback of Uniswap v4 liquidity positions on Robinhood Chain. A liquidity provider sells
their position to a financier, leases it straight back for a fixed rent, keeps the swap fees for the
length of the lease, and may buy it back at a price agreed upfront. Nothing is lent and nothing is
liquidated.

The point is to keep the product experience of a collateralised loan, cash now against a productive
asset, while the contract is a sale plus a lease plus a buyback promise rather than a pledged loan
with a fixed surcharge. The compliance analysis is in section 6 of the spec.

**Status: prototype.** It builds with solc 0.8.28. 42 unit tests pass against mocks, including a
stateful fuzz over random action sequences, and 5 integration tests pass forked against the real
Uniswap v4 PositionManager on Robinhood Chain. It has not been audited and the structure has not been
reviewed by a compliance committee. Do not deploy it as it stands.

## The blocker to know before anything else

Robinhood Chain's Stock Tokens are not tokenised equities. Per the official documentation they are
tokenised debt securities issued by Robinhood Assets (Jersey) Limited, with no voting rights, no
claim on the underlying share, and barred from US persons. Two consequences:

- **On the SEC side.** The innovation exemption covers only tokenised NMS stock carrying the same
  rights as an ordinary share. It explicitly excludes synthetic tokens that give price exposure
  alone. Today's Stock Tokens are out of scope.
- **On the compliance side.** A debt security tracking a share price is a receivable, not ownership.
  Making a market in one is what the analysis in the spec rules out.

Both criteria point the same way. The vault itself admits any pool, because an allowlist inside an
immutable contract is either frozen forever or governed by somebody. The judgement sits in
`ScreeningList` instead, which the vault never reads: for now it covers crypto pairs judged
permissible, WETH/USDG for instance, and later full-rights tokenised equities once they exist on the
chain. It carries an `assetClass` and a `screeningRef` so the decision is recorded pair by pair, and
whoever is funding a deal decides whether to consult it.

## How it works

1. **Listing.** The liquidity provider offers their position NFT with a price, a total rent for the
   term, a buyback price and a duration. The NFT moves into the vault.
2. **Funding.** A financier pays the price and becomes the owner of the position. The seller receives
   the price less the prepaid rent. The rent stays in escrow and streams to the financier second by
   second.
3. **The lease.** The lessee collects the position's swap fees as often as they like. They can never
   withdraw liquidity. If the underlying token is frozen by its issuer, the rent stops accruing.
4. **Maturity.** The lessee buys the position back at the agreed price, any time until the grace
   window closes, and unaccrued rent is refunded to them. Otherwise, after the grace window, the
   financier takes delivery of what already belongs to them.

Every payment is a balance to withdraw, never a forced transfer. The vault has no owner and no
upgrade path, and takes no fee of its own.

Each side may name a **builder** and pay them a flat amount for bringing them the deal, in the
manner of Hyperliquid: the seller names one in the terms and pays out of their proceeds, the
financier names one when funding and pays on top of the price. Name nobody and nothing is charged.
Neither fee ever reaches the vault, and each is capped at a hundredth of the price so a front end
filling that field in cannot help itself. See section 6b of the specification.

## Layout

```
src/LeaseVault.sol          the core contract, no owner
src/ScreeningList.sol       a published opinion about which pools are fit to deal in, read by nobody
src/TestUSDG.sol            a settlement token for test networks, mintable by anyone
src/testnet/                a second test token, and a faucet that hands out live test positions
src/interfaces/             minimal surfaces of PositionManager, StateView, ERC-20
src/libraries/Types.sol     v4 types copied over, PositionInfo decoding, actions
test/LeaseVault.t.sol       unit tests
test/Invariants.t.sol       stateful fuzz over random action sequences
test/fork/VaultFork.t.sol   integration tests forked against Robinhood Chain
test/fork/FaucetFork.t.sol  the faucet and a whole deal, forked against the testnet vault
test/mocks/                 USDG, a pausable token, a PositionManager and a StateView
script/Deploy.s.sol         the deployment itself
script/DeployFaucet.s.sol   the test position faucet, test networks only
deploy.sh                   one command, with the checks and the guards around it
deploy-faucet.sh            the same, for the faucet
docs/SPEC.md                specification, compliance analysis, regulatory context
```

## Running it

The project has no external dependency: the handful of Foundry cheatcodes used are declared in
`test/utils/MiniTest.sol`. With Foundry installed, under WSL for instance:

```bash
forge test --offline -vv
```

Integration tests against the live Uniswap v4 deployment. The script picks a live, in-range,
wide-range position on its own using `../lp-api`. Nothing is sent to the chain.

```bash
./fork-test.sh
```

Before any deployment, confirm the addresses are still what they claim. A young chain redeploys
its infrastructure, and the vault cannot tell an empty address from a silent one:

```bash
./verify-addresses.sh            # mainnet, 4663
./verify-addresses.sh testnet    # 46630
```

Deployment. The vault takes no owner and no parameters of its own, so there is nothing to configure
afterwards and nobody to ask:

```bash
PRIVATE_KEY=0x... ./deploy.sh testnet
```

The key is read from the environment and written nowhere: not to a file, not to the command line
where `ps` would show it, and not to the broadcast log. The script verifies the addresses first,
refuses a deployer holding no gas, and prints the line to paste into `app/config.js`, which is the
whole of making the front end live on that chain.

`./deploy.sh mainnet` additionally refuses unless `CONFIRM=no-audit-i-accept` is set. Nothing here
has been audited, that is said everywhere else in this repository, and the one deployment that
cannot be undone should not be reachable by habit.

Add `SCREENING_OWNER=0x...` to deploy a `ScreeningList` beside it. That is a separate contract
publishing one party's opinion of which pools are fit to deal in; the vault never reads it, and
leaving it out changes nothing about how the vault behaves.

### The settlement token off mainnet

Robinhood Chain's testnet carries the same Uniswap v4 deployment at the same addresses as its
mainnet, and has no USDG. So `USDG` is a variable rather than a constant: set it to a token that
exists on the chain you are deploying to, or leave it unset and the deploy creates a `TestUSDG`,
which has six decimals like the token it stands in for and which anyone can mint without limit.
That last property is the point — a test token that could be scarce is a test token somebody will
eventually try to sell. On mainnet an unset `USDG` means USDG, never an invented one.

### Test positions

A tester needs a position to lease, and a test network has almost none. `deploy-faucet.sh` deploys
a second test token, tETH, and `TestPositionFaucet`, which opens a tETH/tUSDG pool at 3,000 tUSDG
per tETH. Each call to `give()` mints a position six percent either side of the current price to
the caller, then trades a round trip through the pool so every position in range earns swap fees.
It has no owner, and its constructor refuses mainnet.

```bash
PRIVATE_KEY=0x... ./deploy-faucet.sh testnet
forge test --match-path "test/fork/FaucetFork*" --fork-url https://rpc.testnet.chain.robinhood.com -vv
```

## Addresses used on Robinhood Chain (4663)

| Contract | Address |
|---|---|
| USDG | 0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168 |
| Uniswap v4 PositionManager | 0x58daec3116aae6D93017bAAea7749052E8a04fA7 |
| Uniswap v4 StateView | 0xF3334192D15450CdD385c8B70e03f9A6bD9E673b |
| Uniswap v4 PoolManager | 0x8366a39CC670B4001A1121B8F6A443A643e40951 |

RPC: https://rpc.mainnet.chain.robinhood.com. Explorer: https://robinhoodchain.blockscout.com. USDG
sits behind an upgradeable proxy and exposes `paused()`: if its issuer ever pauses it, rent stops
accruing on every deal at once and no USDG moves until it resumes.

## References

- [SEC, statement on the innovation exemption](https://www.sec.gov/newsroom/speeches-statements/uyeda-statement-innovation-exemption-091726)
- [SEC press release 2026-90](https://www.sec.gov/newsroom/press-releases/2026-90-sec-issues-innovation-exemption-facilitate-trading-tokenized-nms-stock-request-comment)
- [CFTC, no-action for passive software providers](https://www.cftc.gov/PressRoom/PressReleases/9300-26)
- [Robinhood Chain, Stock Tokens](https://docs.robinhood.com/chain/stock-tokens/)
- [Uniswap v4, PositionManager](https://developers.uniswap.org/docs/protocols/v4/guides/position-manager)
