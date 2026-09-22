# Deploying

The vault takes no owner and no parameters of its own, so deploying it is one command, and there is
nothing to do afterwards.

## Requirements

- [Foundry](https://getfoundry.sh), under Linux or WSL.
- A funded deployer key, in the environment.

The project has no external dependency: the contracts import no Solidity library.

## Run the tests first

```bash
./check.sh          # everything: contracts, API, app codec, servers
./check.sh --fork   # plus integration tests against live Robinhood Chain state
```

## Deploy

```bash
cd lease-vault
read -rs PRIVATE_KEY && export PRIVATE_KEY && ./deploy.sh testnet; unset PRIVATE_KEY
```

The script:

1. checks the Uniswap v4 addresses against the chain,
2. refuses a deployer with no gas,
3. deploys `LeaseVault`, and off mainnet a `TestUSDG` when no settlement token is given,
4. prints the lines to paste into `app/config.js` under the chain's entry.

The key is read from the environment and written nowhere: not to a file, not to the command line
where `ps` would show it, and not to the broadcast log.

| Variable | Effect |
|---|---|
| `USDG` | settlement token to use. Unset off mainnet: a `TestUSDG` is created. Unset on mainnet: USDG |
| `RPC` | override the chain's RPC endpoint |
| `SCREENING_OWNER` | also deploy a `ScreeningList`, a published opinion about pools that the vault never reads |
| `CONFIRM=no-audit-i-accept` | required for `mainnet`, which is refused without it |

## Local

`app/devchain.sh` forks mainnet into a local anvil, deploys the vault against the real USDG and the
real v4 contracts, and hands a live position to a seller account and USDG to a financier account, so
every screen of the app can be used before anything is deployed anywhere.

```bash
cd app && ./devchain.sh
python3 dev_server.py
```
