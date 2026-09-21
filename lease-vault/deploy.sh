#!/usr/bin/env bash
# Deploys LeaseVault, in one command.
#
#   PRIVATE_KEY=0x... ./deploy.sh testnet     Robinhood Chain testnet, 46630
#   PRIVATE_KEY=0x... RPC=http://127.0.0.1:8545 ./deploy.sh local
#   PRIVATE_KEY=0x... ./deploy.sh mainnet     refuses without CONFIRM, see below
#
# Optional:
#   USDG=0x...             settlement token. Unset off mainnet, a TestUSDG is created.
#   SCREENING_OWNER=0x...  also deploy a ScreeningList owned by this address.
#
# The key is read from the environment and never written anywhere: not into a file, not into the
# command line where `ps` would show it, and not into the broadcast log, which forge keeps under
# cache/ for exactly that reason and which .gitignore already excludes.
set -uo pipefail
export PATH="$HOME/.foundry/bin:$PATH"
cd "$(dirname "$0")" || exit 1

NETWORK="${1:-}"
case "$NETWORK" in
  testnet) RPC="${RPC:-https://rpc.testnet.chain.robinhood.com}" ;;
  mainnet) RPC="${RPC:-https://rpc.mainnet.chain.robinhood.com}" ;;
  local)   RPC="${RPC:-http://127.0.0.1:8545}" ;;
  *)       echo "usage: PRIVATE_KEY=0x... $0 {testnet|mainnet|local}"; exit 1 ;;
esac

die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

[ -n "${PRIVATE_KEY:-}" ] || die "set PRIVATE_KEY in the environment; this script will not read a key from a file"

CHAIN=$(cast chain-id --rpc-url "$RPC" 2>/dev/null) || die "no answer from $RPC"
DEPLOYER=$(cast wallet address --private-key "$PRIVATE_KEY" 2>/dev/null) || die "that is not a private key"
BALANCE=$(cast balance "$DEPLOYER" --rpc-url "$RPC")

say "about to deploy"
echo "  chain     $CHAIN via $RPC"
echo "  deployer  $DEPLOYER"
echo "  balance   $BALANCE wei"
[ "$BALANCE" = "0" ] && die "the deployer holds no gas on this chain"

# Nothing here is audited and the project says so everywhere else, so mainnet asks out loud rather
# than letting a habit carry somebody past the one deployment that cannot be undone.
if [ "$CHAIN" = "4663" ] && [ "${CONFIRM:-}" != "no-audit-i-accept" ]; then
  die "chain 4663 is mainnet and nothing here has been audited.
     If that is really the intention: CONFIRM=no-audit-i-accept $0 $NETWORK"
fi

say "checking the addresses first"
RPC="$RPC" ./verify-addresses.sh "$RPC" || die "stopping: the addresses did not check out"

say "deploying"
OUT=$(forge script script/Deploy.s.sol:Deploy \
        --rpc-url "$RPC" --broadcast --private-key "$PRIVATE_KEY" 2>&1) || {
  echo "$OUT" | tail -30
  die "the deployment failed"
}

BROADCAST="broadcast/Deploy.s.sol/$CHAIN/run-latest.json"
[ -f "$BROADCAST" ] || die "no broadcast log at $BROADCAST"

say "deployed"
python3 - "$BROADCAST" "$CHAIN" <<'PY'
import json, sys

log, chain = json.load(open(sys.argv[1])), sys.argv[2]
made = {t["contractName"]: t["contractAddress"] for t in log["transactions"] if t.get("contractAddress")}
for name in ("TestUSDG", "LeaseVault", "ScreeningList"):
    if name in made:
        print("  %-14s %s" % (name, made[name]))

vault = made.get("LeaseVault")
if vault:
    print()
    print("  Put these into app/config.js, under chains.%s, and the front end is live there:" % chain)
    print()
    print('    vault: "%s",' % vault)
    if "TestUSDG" in made:
        print('    usdg:  "%s",   // the test token, worthless by design' % made["TestUSDG"])
    print()
    print("  The page needs both: a chain with a vault and no settlement token cannot pay for")
    print("  anything, so it stays in the state that draws no buttons.")
    print()
    print("  Check it answers before you tell anybody:")
    print("    cast call %s 'dealCount()(uint256)' --rpc-url <rpc>" % vault)
PY
