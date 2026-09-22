# Builder codes

The vault takes no fee. It has no owner and no address it pays. But whoever brings a party to a deal,
a front end, an agent, a desk, can be paid for it, by that party, out of that party's own money.

This works the way builder codes work on Hyperliquid: each side names its own builder, and each side
pays its own.

## The two sides

| Side | Named in | Paid | From |
|---|---|---|---|
| Seller | the listing terms, `builder` and `builderFee` | at funding | the seller's proceeds |
| Financier | the `fund(dealId, builder, builderFee)` call | at funding | on top of the price |

Neither side ever pays the other side's builder, and neither fee reaches the vault. Name nobody, the
zero address, and nothing is charged.

## The cap

Each fee is capped at **one hundredth of the sale price**. The party paying rarely builds the
transaction they sign, so a front end filling the field in should not be able to help itself to an
unbounded share.

A fee with no builder is refused (`BadBuilderFee`): it would burn money.

## As a builder

Your address simply receives a USDG balance in the vault when the deal is funded. Withdraw it with
`withdrawUSDG`, like any other balance. A `BuilderPaid` event records every payment, with
`sellerSide` telling you which side paid it.

```solidity
event BuilderPaid(uint256 indexed dealId, address indexed builder, uint128 fee, bool sellerSide);
```
