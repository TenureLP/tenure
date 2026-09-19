# App

The deal flow, as a page. No framework, no build step, no dependency: the same rule the contracts
and the services follow, and for the same reason.

```
index.html      the page, styles included
app.js          wallet, lookup, rendering
assets/         the mark
dev_server.py   local preview, standard library only
```

```bash
python dev_server.py        # http://127.0.0.1:8420
```

`?id=2908273` in the address bar values that position on load, which makes a valuation shareable.

## What works today

Valuing a position: what it holds, what its range actually earned over a day of chain history, and
the terms it could be offered on. That reads the live API and needs no wallet and no contract.

Connecting a wallet works and checks the chain, and there is currently nothing to sign.

## What does not

Listing, funding, collecting and buying back all need `LeaseVault`, and **no contract is deployed on
any chain**. The page says so rather than showing controls that cannot work.

## Finding a position

There is no "your positions" screen, and it is not an oversight. The v4 `PositionManager` does not
implement `ERC721Enumerable`: `balanceOf` answers, `tokenOfOwnerByIndex` does not, so an address
cannot be turned into a list of its positions by asking the chain. The usual answer is an indexer
built from `Transfer` logs, and `eth_getLogs` is refused by every RPC endpoint available here.

So a seller pastes an id, which their wallet or the explorer will tell them. The financier side will
need none of this: `LeaseVault` exposes `dealCount`, so every open listing is enumerable directly.
