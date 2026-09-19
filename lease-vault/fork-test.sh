#!/usr/bin/env bash
# Integration tests against the live Uniswap v4 deployment on Robinhood Chain (state is forked, nothing is sent).
#   ./fork-test.sh                 picks a live, in-range, wide-range USDG position with ../lp-api
#   ./fork-test.sh 2937765         use this position id
export PATH="$HOME/.foundry/bin:$PATH"
cd "$(dirname "$0")" || exit 1
if [ -n "$1" ]; then
  export FORK_TOKEN_ID="$1"
else
  export LPVAL_SNAP_DB=/tmp/lpval_snap.sqlite
  FORK_TOKEN_ID=$(cd ../lp-api && python3 -m lpval find --scan 1500 --min-usdg 200 --max 1 --wide | awk '$1 ~ /^[0-9]+$/ {print $1; exit}')
  [ -z "$FORK_TOKEN_ID" ] && { echo "no suitable live position found"; exit 1; }
  export FORK_TOKEN_ID
fi
echo "using position $FORK_TOKEN_ID"
forge test --match-path "test/fork/*" --fork-url "${RPC:-https://rpc.mainnet.chain.robinhood.com}" -vv
