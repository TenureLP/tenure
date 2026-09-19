#!/usr/bin/env bash
# Asks a deployed ERC-20 whether it has any of the powers a holder should care about.
#
#   ./check-token.sh                              the live TEN
#   ./check-token.sh 0xabc... [rpc-url]           any other token
#
# It calls each selector and reports whether the contract answers. A contract that answers none of
# them cannot be paused, minted, frozen, taxed or upgraded out from under you by anybody, because
# there is nobody with the power to do it.
#
# This is what the public claim about TEN rests on, so it ships with the claim.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

TOKEN="${1:-0xD66C5B89fF7b95ad6E73a0B183d74579EB9d6cCb}"
RPC="${2:-${LPVAL_RPC:-https://rpc.mainnet.chain.robinhood.com}}"

LPVAL_RPC="$RPC" python3 - "$TOKEN" <<'PY'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath("../lp-api")), "lp-api"))
sys.path.insert(0, "../lp-api")
from lpval import abi
from lpval.rpc import Rpc

token = sys.argv[1]
rpc = Rpc(os.environ["LPVAL_RPC"])

# Anything that lets somebody else decide what happens to your balance.
POWERS = [
    # ownership
    "owner()", "getOwner()", "admin()", "authority()",
    "transferOwnership(address)", "renounceOwnership()",
    # supply
    "mint(address,uint256)", "minter()", "setMinter(address)",
    # freezing
    "pause()", "unpause()", "paused()",
    "blacklist(address)", "isBlacklisted(address)", "setBlacklist(address,bool)",
    # taxing
    "setFee(uint256)", "setTaxRate(uint256)", "excludeFromFee(address)",
    # gating
    "tradingEnabled()", "setTradingEnabled(bool)", "maxWallet()", "maxTransaction()",
    # replacing the code
    "upgradeTo(address)", "implementation()",
]


def answers(sig):
    try:
        r = rpc.eth_calls([(token, abi.call_data(sig))])[0]
    except Exception:
        return False
    return isinstance(r, bytes)


def read_str(sig):
    try:
        b = rpc.eth_calls([(token, abi.call_data(sig))])[0]
    except Exception:
        return None
    if not isinstance(b, bytes) or len(b) < 64:
        return None
    off = int.from_bytes(b[:32], "big")
    n = int.from_bytes(b[off:off + 32], "big")
    return b[off + 32:off + 32 + n].decode("utf-8", "replace")


name, symbol = read_str("name()"), read_str("symbol()")
print("  token   %s" % token)
print("  name    %s (%s)" % (name, symbol))

found = [s for s in POWERS if answers(s)]
print("  checked %d privileged selectors" % len(POWERS))
print()

if found:
    for s in found:
        print("    PRESENT  %s" % s)
    print()
    print("  %d of them exist. Somebody can use them." % len(found))
    raise SystemExit(1)

print("  none of them exist.")
PY
