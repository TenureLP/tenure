# App

The deal flow, as a page. No framework, no build step, no dependency: the same rule the contracts
and the services follow, and for the same reason.

```
index.html      the page, styles included
config.js       what it talks to: chain, API, token addresses, vault
abi.js          generated from the compiled contract; never edited by hand
eth.js          ABI coder and JSON-RPC, written out
wallet.js       the wallet, and the only place a transaction is sent from
app.js          the three screens
assets/         the mark
dev_server.py   local preview, standard library only
devchain.sh     a forked chain with the vault on it, to use the page against
make-abi-js.py  regenerates abi.js
```

```bash
python dev_server.py        # http://127.0.0.1:8420
```

`?id=2908273` values that position on load, which makes a valuation shareable.

## The three screens

**Value** asks the API what a position holds, what its range has actually earned over a day of
chain history, and what terms it could be offered on. It needs no wallet and no contract. When a
vault is configured and you are the position's owner, the same screen carries the listing form,
filled in from those terms and every field yours to overwrite.

**Market** reads the vault directly: `dealCount`, then every deal. The vault numbers deals from one
and never deletes one, so the whole market is enumerable with no indexer and no server.

**You** is everything you are a party to, on either side, plus what the vault is holding for you.
The actions offered are the ones the contract will accept from your address in that deal's state,
and nothing else is drawn.

## Chains

`config.js` holds one entry per chain, and the page works on whichever one is selected: from
`?chain=`, from the connected wallet when its chain is configured, or the default. When more than
one chain is configured a selector appears in the header.

A chain becomes usable when it has **both** a `vault` and a settlement token. Either one missing
and the page says so rather than drawing controls that would revert. `lease-vault/deploy.sh`
prints the two lines to paste.

| | 4663, mainnet | 46630, testnet |
|---|---|---|
| Uniswap v4 | canonical addresses | **the same addresses**, checked |
| Settlement token | USDG | none, so the deploy creates a TestUSDG anyone can mint |
| Valuation API | yes | **no** |
| Vault | not deployed | not deployed |

### Why the testnet has no valuation

The API prices a position in USDG by reading USDG pools. The testnet has neither. So on a chain
with no `api`, the opening screen stops offering to value anything and asks for terms instead: you
paste a position id, it confirms from the chain who holds it, and you write the price, the buyback
and the rent yourself.

That is not a lesser mode. The vault is the thing that checks a listing, and every write is
dry-run with `eth_call` first, so a refusal arrives named — `BuybackAboveSale`, `OutOfRange`,
`NoLiquidity` — before any gas is spent. The form checks the same bounds client-side as a
courtesy, never as the authority.

## Talking to the chain

Reads go over plain JSON-RPC, so the page works with no wallet at all: somebody can look at a deal
before deciding whether to have an opinion about it. Only the acts that change something need a
key, and a key belongs in the wallet.

Every write is dry-run with `eth_call` first. A revert costs nothing to find that way, and the
vault answers with a named error, so "the transaction failed" becomes "the contract refused:
BuybackAboveSale" before anybody pays for a block.

Approvals are for the exact amount needed. An unlimited approval is convenient once and permanent
afterwards, and this vault is not special enough to deserve one.

`abi.js` is generated from `lease-vault/out/LeaseVault.sol/LeaseVault.json`, so the selectors the
page calls, the field order it decodes a deal with, and the error names it prints all come from the
contract rather than from a copy of it. `check.sh` fails if the two disagree.

## A chain to use it against

```bash
./devchain.sh               # picks a live position with ../lp-api
./devchain.sh 2937765       # or use this one
```

It forks Robinhood Chain into a local anvil, deploys `LeaseVault` against the **real** USDG, the
real PositionManager and the real StateView, puts a real liquidity position in a seller account and
real USDG in a financier account, and prints the url to open. Every screen then does what it will
do on mainnet, against the same contracts, with nothing sent anywhere.

The whole cycle has been driven through the page this way: list, fund, claim rent, withdraw,
collect the position's fees while the vault holds it, buy back, take the position home.

Two things to know about the fork:

- **It needs an archive endpoint to stay usable.** The public RPC drops historical state within
  minutes, and anvil fetches state lazily at the block it forked from, so the fork dies shortly
  after it is created. `FORK_RPC=... ./devchain.sh` points it at a node that keeps state.
- **The API still answers about mainnet.** It is a deployed service and knows nothing about your
  fork, so a position's owner there is its owner on the real chain. The page asks the chain it is
  configured for and shows that answer instead, because that is the one the buttons act on.

The url carries `?vault=&rpc=&wallet=dev`. The override is read **only when the page is served from
this machine** — anywhere else a link could point the app at somebody else's RPC and somebody else's
"vault", and the first thing that would do is ask for an approval. The development wallet is anvil
signing for its own published test accounts; it exists only when the url asks for it by name, and
the page says so across the top in words, because a fake wallet that is not obviously fake is a way
to lose real money.

## Finding a position

There is no "your positions" screen, and it is not an oversight. The v4 `PositionManager` does not
implement `ERC721Enumerable`: `balanceOf` answers, `tokenOfOwnerByIndex` does not, so an address
cannot be turned into a list of its positions by asking the chain. The usual answer is an indexer
built from `Transfer` logs, and `eth_getLogs` is refused by most of the endpoints available here.

So a seller pastes an id, which their wallet or the explorer will tell them. The financier side
needs none of this, which is why Market works without an indexer.

## Not here yet

`transferFinancierPosition` — a financier selling their ownership while the lease runs — and
`checkpointFreeze`, which is a keeper's job rather than a screen. Both are on the contract and
callable; neither has a button.
