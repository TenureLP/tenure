# Lease Vault

Sale-and-leaseback of Uniswap v4 liquidity positions on Robinhood Chain. A liquidity provider sells
their position to a financier, leases it straight back for a fixed rent, keeps the swap fees for the
length of the lease, and may buy it back at a price agreed upfront. Nothing is lent and nothing is
liquidated.

The point is to keep the product experience of a collateralised loan, cash now against a productive
asset, while the contract is a sale plus a lease plus a buyback promise rather than a pledged loan
with a fixed surcharge. The compliance analysis is in section 6 of the spec.

**Status: prototype.** It builds with solc 0.8.28. 37 unit tests pass against mocks, including a
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

Both criteria point the same way. For v1 the allowlist is limited to crypto pairs judged
permissible, WETH/USDG for instance, and later to full-rights tokenised equities once they exist on
the chain. The screening list carries an `assetClass` and a `screeningRef` so that decision is recorded
pair by pair.

## How it works

1. **Listing.** The liquidity provider offers their position NFT with a price, a total rent for the
   term, a buyback price and a duration. The NFT moves into the vault.
2. **Funding.** A financier pays the price and becomes the owner of the position. The seller receives
   the price less the prepaid rent and a flat protocol fee. The rent stays in escrow and streams to
   the financier second by second.
3. **The lease.** The lessee collects the position's swap fees as often as they like. They can never
   withdraw liquidity. If the underlying token is frozen by its issuer, the rent stops accruing.
4. **Maturity.** The lessee buys the position back at the agreed price, any time until the grace
   window closes, and unaccrued rent is refunded to them. Otherwise, after the grace window, the
   financier takes delivery of what already belongs to them.

Every payment is a balance to withdraw, never a forced transfer. The vault has no owner and no
upgrade path.

## Layout

```
src/LeaseVault.sol          the core contract, no owner
src/ScreeningList.sol       a published opinion about which pools are fit to deal in, read by nobody
src/interfaces/             minimal surfaces of PositionManager, StateView, ERC-20
src/libraries/Types.sol     v4 types copied over, PositionInfo decoding, actions
test/LeaseVault.t.sol       unit tests
test/Invariants.t.sol       stateful fuzz over random action sequences
test/fork/VaultFork.t.sol   integration tests forked against Robinhood Chain
test/mocks/                 USDG, a pausable token, a PositionManager and a StateView
script/Deploy.s.sol         deployment to Robinhood Chain
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

Before any deployment, confirm the hardcoded addresses are still what they claim:

```bash
./verify-addresses.sh
```

Deployment. The vault takes no owner and no parameters of its own, so there is nothing to configure
afterwards and nobody to ask:

```bash
forge script script/Deploy.s.sol --rpc-url robinhood --broadcast --verify
```

Add `SCREENING_OWNER=0x...` to deploy a `ScreeningList` beside it. That is a separate contract
publishing one party's opinion of which pools are fit to deal in; the vault never reads it, and
leaving it out changes nothing about how the vault behaves.

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
