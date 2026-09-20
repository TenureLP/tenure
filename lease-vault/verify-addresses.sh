#!/usr/bin/env bash
# Checks that every address the deploy script will use is really what it claims to be.
# Run before any deployment; addresses on a young chain do get redeployed.
#
#   ./verify-addresses.sh              Robinhood Chain mainnet, 4663
#   ./verify-addresses.sh testnet      Robinhood Chain testnet, 46630
#   RPC=http://127.0.0.1:8545 ./verify-addresses.sh
#
# The testnet carries the same Uniswap v4 deployment at the same addresses and has no USDG, so
# there the settlement token is whatever USDG is set to, or a TestUSDG the deploy will create.
export PATH="$HOME/.foundry/bin:$PATH"
fail=0

case "${1:-mainnet}" in
  testnet) RPC="${RPC:-https://rpc.testnet.chain.robinhood.com}"; EXPECT_CHAIN=46630 ;;
  mainnet) RPC="${RPC:-https://rpc.mainnet.chain.robinhood.com}"; EXPECT_CHAIN=4663 ;;
  *)       RPC="${RPC:-$1}"; EXPECT_CHAIN="${EXPECT_CHAIN:-}" ;;
esac

POSM="${V4_POSITION_MANAGER:-0x58daec3116aae6D93017bAAea7749052E8a04fA7}"
STATE_VIEW="${V4_STATE_VIEW:-0xF3334192D15450CdD385c8B70e03f9A6bD9E673b}"

CHAIN=$(cast chain-id --rpc-url "$RPC" 2>/dev/null)
[ -z "$CHAIN" ] && { echo "no answer from $RPC"; exit 1; }
echo "chain id: $CHAIN"
if [ -n "$EXPECT_CHAIN" ] && [ "$CHAIN" != "$EXPECT_CHAIN" ]; then
  echo "WRONG CHAIN, expected $EXPECT_CHAIN"; exit 1
fi

# On mainnet the settlement token is USDG and nothing else. Anywhere else it is whatever was
# named, and an unnamed one means the deploy will create a TestUSDG.
if [ "$CHAIN" = "4663" ]; then
  USDG="${USDG:-0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168}"
else
  USDG="${USDG:-}"
fi

size_of() { # address -> bytes of code
  local code
  code=$(cast code "$1" --rpc-url "$RPC" 2>/dev/null)
  echo $(( (${#code} - 2) / 2 ))
}

check_code() { # label address
  local n
  n=$(size_of "$2")
  if [ "$n" -lt 1 ]; then printf '  %-22s FAIL  no code at %s\n' "$1" "$2"; fail=1
  else printf '  %-22s ok    %s bytes\n' "$1" "$n"; fi
}

check_call() { # label address "call" "expected substring"
  local out
  out=$(cast call "$2" "$3" --rpc-url "$RPC" 2>&1)
  if [ -n "$4" ] && [[ "$out" != *"$4"* ]]; then
    printf '  %-22s FAIL\n     expected %s, got %s\n' "$1" "$4" "$out"; fail=1
  else
    printf '  %-22s ok    %s\n' "$1" "$(echo "$out" | head -c 60)"
  fi
}

echo "code present:"
check_code "PositionManager" "$POSM"
check_code "StateView" "$STATE_VIEW"
[ -n "$USDG" ] && check_code "settlement token" "$USDG"

echo "behaves as expected:"
check_call "PositionManager.next" "$POSM" "nextTokenId()(uint256)" ""
# Read rather than assumed: this is the one address the vault trusts to tell it where a pool is.
POOL_MANAGER=$(cast call "$STATE_VIEW" "poolManager()(address)" --rpc-url "$RPC" 2>/dev/null)
printf '  %-22s ok    %s\n' "StateView.poolManager" "$POOL_MANAGER"
check_call "PositionManager.pm" "$POSM" "poolManager()(address)" "$POOL_MANAGER"
if [ -n "$USDG" ]; then
  check_call "token.decimals()" "$USDG" "decimals()(uint8)" "6"
  check_call "token.symbol()" "$USDG" "symbol()(string)" ""
fi

echo
if [ -z "$USDG" ]; then
  echo "no settlement token set: the deploy will create a TestUSDG anyone can mint"
fi
[ "$fail" -eq 0 ] && echo "all addresses check out" || { echo "ADDRESSES DO NOT CHECK OUT, do not deploy"; exit 1; }
