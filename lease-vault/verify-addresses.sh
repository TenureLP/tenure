#!/usr/bin/env bash
# Checks that every address hardcoded in script/Deploy.s.sol is really what it claims to be on
# Robinhood Chain. Run before any deployment; addresses on a young chain do get redeployed.
export PATH="$HOME/.foundry/bin:$PATH"
RPC="${RPC:-https://rpc.mainnet.chain.robinhood.com}"
fail=0

check() { # label address "call" "expected substring"
  local out
  out=$(cast call "$2" "$3" --rpc-url "$RPC" 2>&1)
  if [ -n "$4" ] && [[ "$out" != *"$4"* ]]; then
    printf '  %-22s %s\n     expected %s, got %s\n' "$1" "FAIL" "$4" "$out"; fail=1
  else
    printf '  %-22s ok   %s\n' "$1" "$(echo "$out" | head -c 60)"
  fi
}

echo "chain id: $(cast chain-id --rpc-url "$RPC")  (expect 4663)"
[ "$(cast chain-id --rpc-url "$RPC")" = "4663" ] || { echo "WRONG CHAIN"; exit 1; }

echo "code present:"
for pair in \
  "USDG:0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168" \
  "PositionManager:0x58daec3116aae6D93017bAAea7749052E8a04fA7" \
  "StateView:0xF3334192D15450CdD385c8B70e03f9A6bD9E673b" \
  "PoolManager:0x8366a39CC670B4001A1121B8F6A443A643e40951"; do
  name=${pair%%:*}; addr=${pair##*:}
  size=$(cast code "$addr" --rpc-url "$RPC" | wc -c)
  if [ "$size" -lt 10 ]; then printf '  %-22s FAIL  no code at %s\n' "$name" "$addr"; fail=1
  else printf '  %-22s ok    %s bytes of code\n' "$name" "$(( (size - 3) / 2 ))"; fi
done

echo "behaves as expected:"
check "USDG.symbol()"        0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168 "symbol()(string)"   "USDG"
check "USDG.decimals()"      0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168 "decimals()(uint8)"  "6"
check "PositionManager.next" 0x58daec3116aae6D93017bAAea7749052E8a04fA7 "nextTokenId()(uint256)" ""
check "StateView.poolManager" 0xF3334192D15450CdD385c8B70e03f9A6bD9E673b "poolManager()(address)" "0x8366a39CC670B4001A1121B8F6A443A643e40951"

echo
[ "$fail" -eq 0 ] && echo "all addresses check out" || echo "ADDRESSES DO NOT CHECK OUT, do not deploy"
exit $fail
