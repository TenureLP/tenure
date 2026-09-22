# Errors

The vault reverts with named custom errors. The app decodes each one and shows it before your wallet
opens, because every transaction is dry-run with `eth_call` first.

## Listing

| Error | Cause |
|---|---|
| `BadTerm` | term outside 1 to 30 days |
| `BadGrace` | grace outside 24 hours to 7 days |
| `BadListingDuration` | listing duration zero or above 30 days |
| `BadFrozenCap` | `maxFrozenBps` above 5000 |
| `BadProbe` | `freezeProbe` other than 0 or 1 |
| `BadEconomics` | price, rent or buyback is zero, or `rent + builderFee` is not below the price |
| `BuybackAboveSale` | buyback price above the sale price. See [the buyback rule](/concepts/buyback) |
| `BadBuilderFee` | a fee with no builder, or a fee above a hundredth of the price |
| `HasSubscriber` | the position has a subscriber attached |
| `NoLiquidity` | the position holds no liquidity |
| `OutOfRange` | the pool's current tick is outside the position's range (also checked at funding) |
| `PositionNotHeld` | the NFT did not arrive in the vault |

## Deal lifecycle

| Error | Cause |
|---|---|
| `NotListed` | the deal is not open for funding or cancelling |
| `NotActive` | the deal is not in its lease |
| `ListingExpired` | the offer's funding window has closed |
| `SelfDeal` | the seller trying to fund their own deal, or a financier selling their side to the seller |
| `NotSeller` | only the seller (lessee) can do this |
| `NotFinancier` | only the financier can do this |
| `LeaseEnded` | fees can only be collected during the term |
| `GraceNotOver` | `release` before the term and the grace window are both over |

## Payouts and misc

| Error | Cause |
|---|---|
| `NothingOwed` | no balance, no position owed, or no new rent to claim |
| `ZeroAddress` | a zero address in the constructor, or transferring the financier side to the zero address or the vault |
| `Reentrancy` | a call re-entered the vault |

## Selectors

To decode a revert by hand, `cast sig` gives the selector of any of them:

```bash
cast sig "BuybackAboveSale()"
# 0x8fc8ee31
```
