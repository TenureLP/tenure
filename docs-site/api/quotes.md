# Quotes

`GET /v1/position/{tokenId}/quote` adds a `quote` object to the valuation: a starting point for a
listing, not a promise that anybody will fund it.

## Parameters

| Query | Default | Meaning |
|---|---|---|
| `term` | `7` | lease length in days |
| `haircut` | `0.2` | discount of the sale price to market value |
| `rentShare` | `0.5` | share of the expected fees over the term charged as rent |
| `lookbackHours` | `24` | window the fee rate is measured over |

## How the terms are derived

```
sale price = market value × (1 − haircut)
buyback    = sale price
rent       = fees per day × term × rentShare
```

The buyback always equals the sale price: the vault refuses anything above it, and below it is for the
parties to agree.

With the defaults, the seller keeps half the fees they expect over the lease and pays the other half
as rent, and the financier buys at 80% of market value.

## Example

```bash
curl "https://api-production-9e87.up.railway.app/v1/position/3093793/quote?term=7"
```

```json
"quote": {
  "available": true,
  "termDays": 7,
  "inputs": { "haircut": 0.2, "rentShareOfExpectedFees": 0.5 },
  "marketValueUSDG": 6926.95,
  "suggestedSalePriceUSDG": 5541.56,
  "suggestedBuybackPriceUSDG": 5541.56,
  "expectedFeesOverTermUSDG": 491.05,
  "suggestedRentUSDG": 245.52,
  "feeRateLowConfidence": false,
  "eligibility": { "inRange": true, "noSubscriber": true },
  "disclaimer": "Indicative model output. Not a guarantee of funding or of resale value."
}
```

## When there is no quote

`available` is `false`, with a `reason`, when:

- the pair has no USDG, so there is no value to price against,
- the position holds no liquidity,
- the fee rate is not usable, so no rent can be derived. The vault refuses a listing with no rent, so
  a price without one would not be a set of terms anybody could act on.

Check `feeRateLowConfidence` before relying on a rent: a rent measured over eight minutes of history is
not one measured over a day.
