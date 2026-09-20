# The Olanas payments MCP, and what it means here

Notes taken on 20 September 2026 from the public branch `codex/olanas-payments-mcp` of
`olanass/web`, from `olanas.xyz`, and from this repository.

## What it is

A local MCP server plus a companion wallet. One command —

```
npx --yes github:olanass/web
```

— creates an EVM key on the user's own machine, encrypts it into a local keystore, and registers
the server with the MCP client of their choice. The owner then enables a bounded spending session
in the companion: a payment token, a per-call cap, a total budget, gas caps and an expiry. After
that an agent can call `search_services` and `request_paid_api`, and the payment happens without a
wallet prompt per call.

It is not custodial, not hosted, and explicitly not endorsed by Robinhood. Session limits are
enforced by the application rather than on chain, which their README says plainly.

## Why it matters here

It is the demand side of the thing this API was built for, and it did not exist last week.

The launchpad still lists exactly one service. So the first paid API any of those agents can buy,
on the day they install it, is this one. That is worth more than the listing was on its own: a
listing is a page, this is a client with one command behind it.

It speaks only this launchpad's `onchain-tx` scheme — their README rules out `exact` and `upto`.
That is the scheme this API already answers in, which is why nothing had to change here to be
compatible with it.

## The two ends do not ask for the same proof

Read from the two services rather than from either README:

```bash
curl -s 'https://olanas.xyz/x402/tenure-position-valuation?tokenId=1' | jq '.accepts[0].extra.proof'
# "confirmed-transaction"

curl -s 'https://api-production-9e87.up.railway.app/v1/position/1/quote' | jq '.accepts[0].extra.proof'
# "confirmed-transaction+payer-signature"   (when the paywall is on)
```

Same scheme name, different proof. This paywall additionally mints a nonce per route and requires
a signature from the paying account over the transaction, the resource and that nonce;
`lp-api/lpval/paywall.py` explains at its top why, and has the tests for it.

We have written to Olanas about the difference and what we think it costs. Nothing further is
recorded here until they have decided what to do, because a gap in somebody else's product is
theirs to close first. The service shows `requests: 0` and `revenue: 0`, the MCP is on a branch,
and no package is published, so nothing has been lost.

## What changed here because of it

Post 4 of the launch thread said the proof carries a nonce the service issued and a signature from
the paying account. That is true of this API and not true of the path a buyer actually takes, so
it claimed a protection the buyer does not get. It was replaced with a post inviting the reader to
check the whole thread for free against the public instance, and it goes back when the sentence is
true end to end.

Worth knowing when reading the OpenAPI, which documents 402 on both position routes: the public
instance runs with `paywall: false`, and the paid route is the gateway's. The capability is real
and tested; it is not what is switched on in front of the deployment people actually call.
