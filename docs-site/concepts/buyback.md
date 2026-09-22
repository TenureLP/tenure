# The buyback rule

::: info The rule
`buybackPrice` can never be greater than `price`. A listing that tries is refused with
`BuybackAboveSale`.
:::

## Why it exists

The financier is paid **rent**, for the use of the position during the lease. If the buyback price
could sit above the sale price, the difference would be a second, guaranteed payment for nothing but
the passage of time: cash out today, more cash back later, whatever happens in between. That is a
loan with interest, dressed as a sale.

Left to the market, financiers would simply fund only the listings that carry such a spread. So the
restraint cannot be a guideline or a front-end default; it has to be in the contract. And because the
vault has no owner, nobody could police it later. It is a constant of the code.

## What remains possible

- A buyback **equal** to the price, the usual case: the seller gets back exactly what they sold.
- A buyback **below** the price, if the two parties want it.

## What the financier is exposed to

Owning the position is a real risk. If the lessee does not buy back, the financier holds a liquidity
position whose value has moved with the market. If it is worth less than they paid, that is their
loss, and they have no claim on the lessee for it. That exposure is what makes the deal a sale rather
than a secured loan: nobody guarantees the financier their money back.
