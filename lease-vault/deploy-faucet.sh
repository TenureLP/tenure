#!/usr/bin/env bash
# Deploys the test position faucet: a second test token and a pool of the two, from which anyone
# gets a live Uniswap v4 position in one call. Test networks only.
#
#   PRIVATE_KEY=0x... ./deploy-faucet.sh testnet     Robinhood Chain testnet, 46630
#   PRIVATE_KEY=0x... RPC=http://127.0.0.1:8545 ./deploy-faucet.sh local
#
# Optional:
#   TUSDG=0x...   the TestUSDG deploy.sh created. Defaults to the one on Robinhood Chain testnet.
#
# The key is read from the environment and never written anywhere, as in deploy.sh.
set -uo pipefail
export PATH="$HOME/.foundry/bin:$PATH"
cd "$(dirname "$0")" || exit 1

NETWORK="${1:-}"
case "$NETWORK" in
  testnet) RPC="${RPC:-https://rpc.testnet.chain.robinhood.com}" ;;
  local)   RPC="${RPC:-http://127.0.0.1:8545}" ;;
  *)       echo "usage: PRIVATE_KEY=0x... $0 {testnet|local}"; exit 1 ;;
esac

die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

[ -n "${PRIVATE_KEY:-}" ] || die "set PRIVATE_KEY in the environment; this script will not read a key from a file"

CHAIN=$(cast chain-id --rpc-url "$RPC" 2>/dev/null) || die "no answer from $RPC"
# A faucet of worthless positions has no business beside real ones. The contract refuses too.
[ "$CHAIN" = "4663" ] && die "chain 4663 is mainnet: the faucet is for test networks only"
DEPLOYER=$(cast wallet address --private-key "$PRIVATE_KEY" 2>/dev/null) || die "that is not a private key"
BALANCE=$(cast balance "$DEPLOYER" --rpc-url "$RPC")

say "about to deploy the position faucet"
echo "  chain     $CHAIN via $RPC"
echo "  deployer  $DEPLOYER"
echo "  balance   $BALANCE wei"
[ "$BALANCE" = "0" ] && die "the deployer holds no gas on this chain"

say "deploying"
OUT=$(forge script script/DeployFaucet.s.sol:DeployFaucet \
        --rpc-url "$RPC" --broadcast --private-key "$PRIVATE_KEY" 2>&1) || {
  echo "$OUT" | tail -30
  die "the deployment failed"
}

BROADCAST="broadcast/DeployFaucet.s.sol/$CHAIN/run-latest.json"
[ -f "$BROADCAST" ] || die "no broadcast log at $BROADCAST"

say "deployed"
python3 - "$BROADCAST" "$CHAIN" <<'PY'
import json, sys

log, chain = json.load(open(sys.argv[1])), sys.argv[2]
made = {t["contractName"]: t["contractAddress"] for t in log["transactions"] if t.get("contractAddress")}
for name in ("TestToken", "TestPositionFaucet"):
    if name in made:
        print("  %-19s %s" % (name, made[name]))

faucet = made.get("TestPositionFaucet")
if faucet:
    print()
    print("  Put this into app/config.js, under chains.%s, and the app offers a test position:" % chain)
    print()
    print('    faucet: "%s",' % faucet)
    print()
    print("  Check it hands one out before you tell anybody (this sends a transaction):")
    print("    cast send %s 'give()' --rpc-url <rpc> --private-key <key>" % faucet)
PY
