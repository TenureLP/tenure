#!/usr/bin/env bash
# Runs every check in the repo. Exits non-zero if anything fails.
#   ./check.sh          unit tests only, no network
#   ./check.sh --fork   also the integration tests against live Robinhood Chain state
set -uo pipefail
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.foundry/bin:$PATH"
fail=0

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
note() { if [ "$1" -eq 0 ]; then printf '   ok\n'; else printf '   FAILED\n'; fail=1; fi; }

step "Solidity: build"
(cd lease-vault && forge build --offline >/dev/null); note $?

step "Solidity: unit tests"
(cd lease-vault && forge test --offline); note $?

step "Python: lp-api tests"
(cd lp-api && python3 -m unittest discover -s tests -q); note $?

step "Python: syntax of every module"
python3 -m compileall -q lp-api/lpval landing/api landing/dev_server.py brand/build.py >/dev/null; note $?

step "Landing: waitlist endpoint logic"
python3 - <<'PY'
import sys, os, json, tempfile
sys.path.insert(0, "landing")
os.environ["WAITLIST_FILE"] = os.path.join(tempfile.mkdtemp(), "w.jsonl")
os.environ.pop("WAITLIST_WEBHOOK_URL", None)
os.environ.pop("VERCEL", None)
from api.waitlist import process
cases = [
    (b'{"email":"a@b.co"}', 200), (b'{"email":"a@b.co"}', 200),      # second is the duplicate
    (b'{"email":"nope"}', 400), (b'{', 400),
    (b'{"email":"a@b.co","company":"bot"}', 200),                      # honeypot
]
for body, want in cases:
    got, _ = process(body)
    assert got == want, (body, got, want)
print("   5 cases ok")
PY
note $?

if [ "${1:-}" = "--fork" ]; then
  step "Solidity: fork integration tests"
  (cd lease-vault && ./fork-test.sh); note $?
fi

printf '\n'
[ "$fail" -eq 0 ] && printf '\033[1mall green\033[0m\n' || printf '\033[1msomething failed\033[0m\n'
exit $fail
