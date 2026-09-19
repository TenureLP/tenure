#!/usr/bin/env bash
# Stands up a chain the front end can actually be used against.
#
#   ./devchain.sh              picks a live, in-range, wide-range position with ../lp-api
#   ./devchain.sh 2937765      uses this position
#
# It forks Robinhood Chain into a local anvil, deploys LeaseVault against the real USDG, the real
# PositionManager and the real StateView, then puts a real liquidity position in the hands of a
# seller account and real USDG in the hands of a financier account. From there every screen in the
# app does what it will do on mainnet, against the same contracts, without anything being sent.
#
# The keys below are anvil's published test keys. They are in every Foundry tutorial, they hold
# nothing anywhere, and printing them is the point: this is a sandbox, and it should be obvious.
set -uo pipefail
export PATH="$HOME/.foundry/bin:$PATH"
cd "$(dirname "$0")" || exit 1

RPC=http://127.0.0.1:8545
FORK="${FORK_RPC:-https://rpc.mainnet.chain.robinhood.com}"

# anvil accounts 0 and 1.
SELLER=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
SELLER_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
FINANCIER=0x70997970C51812dc3A010C7d01b50e0d17dc79C8
FINANCIER_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d

USDG=0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168
POSM=0x58daec3116aae6D93017bAAea7749052E8a04fA7
# The PoolManager holds the tokens of every v4 pool on the chain, so it is the one address certain
# to have USDG. Asked of the PositionManager rather than written down: this chain does not use the
# address the other Uniswap deployments do, and a constant here would be a constant that is wrong.
# Taking some breaks its internal accounting, which matters on a chain that exists for ten minutes.

say() { printf "\n\033[1m%s\033[0m\n" "$*"; }
die() { printf "\033[31m%s\033[0m\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------- the chain

if cast chain-id --rpc-url "$RPC" >/dev/null 2>&1; then
  say "anvil is already up on 8545, reusing it"
else
  say "forking $FORK"
  nohup anvil --fork-url "$FORK" --port 8545 --host 127.0.0.1 --silent >/tmp/tenure-anvil.log 2>&1 &
  for _ in $(seq 1 30); do
    cast chain-id --rpc-url "$RPC" >/dev/null 2>&1 && break
    sleep 1
  done
  cast chain-id --rpc-url "$RPC" >/dev/null 2>&1 || die "anvil did not come up; see /tmp/tenure-anvil.log"
fi
echo "  chain $(cast chain-id --rpc-url $RPC) at block $(cast block-number --rpc-url $RPC)"

# ---------------------------------------------------------------- the vault

say "deploying LeaseVault"
( cd ../lease-vault && forge script script/Deploy.s.sol:Deploy --rpc-url "$RPC" --broadcast \
    --private-key "$SELLER_KEY" >/tmp/tenure-deploy.log 2>&1 ) || die "deploy failed; see /tmp/tenure-deploy.log"
VAULT=$(python3 -c "
import json
d = json.load(open('../lease-vault/broadcast/Deploy.s.sol/4663/run-latest.json'))
print([t['contractAddress'] for t in d['transactions'] if t['contractName'] == 'LeaseVault'][0])
")
[ -z "$VAULT" ] && die "no vault address in the broadcast file"
echo "  vault $VAULT"

# ---------------------------------------------------------------- the position

if [ -n "${1:-}" ]; then
  TOKEN_ID="$1"
else
  # Searched through the fork, not through the live chain: the fork is pinned at the block anvil
  # started on, and a position minted after that one exists upstream and nowhere here.
  say "looking for a live position worth leasing"
  TOKEN_ID=$(cd ../lp-api && LPVAL_RPC="$RPC" LPVAL_SNAP_DB=/tmp/lpval_snap.sqlite python3 -m lpval find \
    --scan 1500 --min-usdg 200 --max 1 --wide 2>/dev/null | awk '$1 ~ /^[0-9]+$/ {print $1; exit}')
  [ -z "$TOKEN_ID" ] && die "no suitable live position found; pass one as an argument"
fi
OWNER=$(cast call "$POSM" "ownerOf(uint256)(address)" "$TOKEN_ID" --rpc-url "$RPC") || die "position $TOKEN_ID has no owner"
echo "  position $TOKEN_ID currently held by $OWNER"

say "moving it to the seller"
cast rpc anvil_impersonateAccount "$OWNER" --rpc-url "$RPC" >/dev/null
cast rpc anvil_setBalance "$OWNER" 0xde0b6b3a7640000 --rpc-url "$RPC" >/dev/null
cast send "$POSM" "transferFrom(address,address,uint256)" "$OWNER" "$SELLER" "$TOKEN_ID" \
  --from "$OWNER" --unlocked --rpc-url "$RPC" >/dev/null || die "the transfer was refused"
cast rpc anvil_stopImpersonatingAccount "$OWNER" --rpc-url "$RPC" >/dev/null
echo "  now held by $(cast call "$POSM" "ownerOf(uint256)(address)" "$TOKEN_ID" --rpc-url "$RPC")"

# ---------------------------------------------------------------- the money

say "funding the financier with USDG"
AMOUNT=50000000000  # 50,000 USDG, six decimals
POOL_MANAGER=$(cast call "$POSM" "poolManager()(address)" --rpc-url "$RPC")
echo "  taking it from the pool manager at $POOL_MANAGER"
cast rpc anvil_impersonateAccount "$POOL_MANAGER" --rpc-url "$RPC" >/dev/null
cast rpc anvil_setBalance "$POOL_MANAGER" 0xde0b6b3a7640000 --rpc-url "$RPC" >/dev/null
cast send "$USDG" "transfer(address,uint256)" "$FINANCIER" "$AMOUNT" \
  --from "$POOL_MANAGER" --unlocked --rpc-url "$RPC" >/dev/null || die "USDG would not move"
cast rpc anvil_stopImpersonatingAccount "$POOL_MANAGER" --rpc-url "$RPC" >/dev/null
BAL=$(cast call "$USDG" "balanceOf(address)(uint256)" "$FINANCIER" --rpc-url "$RPC" | awk '{print $1}')
echo "  financier holds $((BAL / 1000000)) USDG"

# ---------------------------------------------------------------- how to use it

say "ready"
cat <<EOF
  vault      $VAULT
  position   $TOKEN_ID        held by the seller
  seller     $SELLER
             $SELLER_KEY
  financier  $FINANCIER
             $FINANCIER_KEY

  python dev_server.py, then open

  http://127.0.0.1:8420/?vault=$VAULT&rpc=$RPC&wallet=dev

  The override is only read when the page is served from localhost, and the dev wallet only exists
  when wallet=dev is asked for. Drop both from the URL and the page is exactly what ships.

  Stop the chain with: pkill -f 'anvil --fork-url'
EOF
