# Tenure

Sale-and-leaseback for Uniswap v4 liquidity positions on Robinhood Chain.

A liquidity provider sells a position NFT to a financier for cash, leases it back for a fixed term against a fixed rent, keeps collecting the pool's swap fees, and holds a promise from the financier to sell it back at a price agreed upfront. No debt is created at any point, so there is nothing to liquidate and no oracle in the deal path. If the lessee does not buy back before the grace window closes, the financier simply takes delivery of the position they already own.

`Tenure` is a working name. Nothing here is deployed, audited, or offered to anyone.

## Layout

| Folder | What it is |
|---|---|
| `lease-vault/` | The contracts. `LeaseVault` has no owner and no upgrade path; `AssetRegistry` holds the policy and is read only at listing time. |
| `lp-api/` | Position valuation over JSON-RPC with exact integer maths, behind an HTTP 402 paywall settled by a confirmed on-chain transfer. Standard library only. |
| `landing/` | Static waitlist page and its endpoint. Not deployed. |
| `brand/` | Logo, avatar, banner and teaser, all generated from `brand/build.py`. |

### Brand files

| File | Use |
|---|---|
| `logo-avatar-1024.png`, `logo-avatar-400.png` | Profile picture. The drawing is pulled inside the circle a service will crop it to. |
| `logo-mark-1024.png`, `logo-mark.svg` | Square icon, for anything not cropped to a circle. |
| `logo-mark-small.svg` | Favicon and 32 px and below: heavier strokes, no price dot. |
| `logo-mark-mono.svg` | One colour, no tile: stamps and watermarks. |
| `logo-horizontal-dark.png`, `logo-horizontal-light.png` | Symbol plus name, on a dark or a light background. |
| `logo-nav.svg` | Compact, transparent, for a site header. |
| `banner-1500x500.png` | Social header. `banner-t1`…`t3` are the alternative text treatments; set `BRAND_BANNER` and re-export to switch. |
| `video/tenure-intro.mp4` | A 16 second teaser, 1920×1080, silent. |

Everything under `brand/` is generated. `brand/build.py` draws the SVGs with the text converted to
outlines, so they render identically without the font installed, and `brand/export.ps1` rasterises
them. Passing a different name to either regenerates the whole set under that name.

## Checks

Everything runs from WSL, where Foundry and Python 3.12 are installed.

```bash
./check.sh
```

```bash
./check.sh --fork
```

The first runs the contract build, 30 Solidity tests including a stateful fuzz over random action sequences, the Python tests, and the waitlist endpoint. The second adds five integration tests against live Uniswap v4 state on chain 4663.

Before any deployment, confirm the addresses the deploy script hardcodes are still what they claim:

```bash
cd lease-vault && ./verify-addresses.sh
```

## What holds, and what does not

Proven by tests: the vault never owes more USDG than it holds, rent paid out never exceeds the rent escrowed at funding, frozen time never exceeds the term, a position is owed to at most one party, the lessee can collect fees but can never withdraw liquidity, and a financier who takes delivery receives a position they can actually unwind.

Not established: no independent audit, no deployment, no economic review of the lease terms under stress, and no formal verification. The registry owner is trusted to allowlist only sound pools.

## Dependencies

None. The contracts use no external Solidity library, the API uses no package outside the Python standard library, and the brand assets need only fontTools and a copy of Bahnschrift. This is deliberate: the smaller the trusted surface, the less there is to audit.
