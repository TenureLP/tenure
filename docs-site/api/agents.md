# Using it from an agent

The valuation API is built to be called by software as much as by the app: an agent managing
liquidity can price a position, read what its range really earns, and get terms it could raise, in
one request. It only reads. It never signs anything and never moves funds.

There are two ways to call it.

| | Through Olanas | Directly |
|---|---|---|
| Endpoint | `https://olanas.xyz/x402/tenure-position-valuation` | `https://api-production-9e87.up.railway.app` |
| Price | 0.003 USDG per request | free today |
| Payment | handled by the Olanas Payments MCP | none, or HTTP 402 if a price is set on your own instance |
| Discovery | listed on the launchpad, found by the agent | you give it the URL |

## Through Olanas

[Olanas](https://olanas.xyz) is an API launchpad on Robinhood Chain. Tenure position valuation is
listed on it:

| | |
|---|---|
| Listing | [olanas.xyz/services/tenure-position-valuation](https://olanas.xyz/services/tenure-position-valuation) |
| Gateway | `https://olanas.xyz/x402/tenure-position-valuation` |
| Price | 0.003 USDG per request |
| Method | `GET` only |
| Chain | Robinhood Chain, `eip155:4663` |

The gateway answers an unpaid request with a standard **x402 version 2** challenge, scheme
`onchain-tx`, and forwards a paid one to the Tenure API.

### The Olanas Payments MCP

Olanas publishes a local MCP server with a companion wallet, so an agent can pay for launchpad
services without a wallet prompt per call:

1. **Install it.** One command, from their repository. It creates an EVM key on your own machine,
   encrypts it into a local keystore, and registers the server with the MCP client you choose:
   Claude, Claude Code, Codex, Gemini, or any other. Follow
   [their README](https://github.com/olanass/web/tree/olanas-payments-mcp) for the current command:
   it is theirs, and it changes with their releases.
2. **Fund and bound it.** Send USDG and a little ETH for gas to the wallet it shows, then enable a
   spending session in the companion: a per-call cap, a total budget, gas caps and an expiry. Nothing
   is spent before you do.
3. **Ask.** The agent calls `search_services` to find Tenure position valuation, then
   `request_paid_api` to pay for it and read the answer.

A prompt as plain as this is enough:

```
Value Uniswap v4 position 3093793 on Robinhood Chain with Tenure,
and tell me what it could raise on a 7-day lease.
```

::: tip Read their documentation, not ours
The MCP is Olanas's software, not Tenure's. Its install command, its session limits and its
security model are described in their repository, and that is where to check them.
:::

## Directly

The public instance runs free, with no key:

```bash
curl https://api-production-9e87.up.railway.app/v1/position/3093793/quote?term=7
```

Everything an agent needs to call it without a human in the loop is in the
**OpenAPI 3.1** document, served by the running build so it cannot drift from it:

```bash
curl https://api-production-9e87.up.railway.app/openapi.json
```

Point an agent framework at that document and every route, parameter and response field is
described, including the `402` envelope. The routes and fields are in the
[overview](/api/), and the terms in [quotes](/api/quotes).

If you run your own instance with a price set, it answers HTTP 402 and expects a signed proof of
payment. See [paying per request](/api/payments).

## From a valuation to a deal

The terms in a quote are shaped exactly like the vault's: a sale price, a buyback equal to it, a rent
for the term. An agent that has valued a position can hand those figures to the
[app](https://app-production-7810.up.railway.app/?id=3093793), or encode a `list` call itself against
the [LeaseVault reference](/contracts/lease-vault).

Listing and funding are writes. They go through a wallet the owner controls, never through the API,
and never through a launchpad.
