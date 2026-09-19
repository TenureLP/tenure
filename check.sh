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
python3 -m compileall -q lp-api/lpval landing/api landing/dev_server.py landing/server.py \
  landing/read_waitlist.py brand/build.py >/dev/null; note $?

step "API: the description matches the service, and both spellings match each other"
# A description nobody checks drifts from the build within a week, and this one is handed to third
# parties as the integration contract. Three layers, the first two needing nothing but the standard
# library: the JSON is read with `json`, the YAML path keys with a regex, and full equality only
# when PyYAML happens to be installed.
python3 - <<'PY'
import json, re, sys
sys.path.insert(0, "lp-api")
from lpval import server

doc = json.load(open("lp-api/openapi.json", encoding="utf-8"))
documented = set(doc["paths"])

served_fixed = set(server._SPEC_FILES) | {"/health"}
templated = {p for p in documented if "{" in p}
assert templated, "no position route documented"
for path in templated:
    assert server._ROUTE.match(path.replace("{tokenId}", "2908254")), "documented, not served: %s" % path

flat = {p for p in documented if "{" not in p}
# /openapi.yml is served as an alias and deliberately not documented twice.
assert flat <= served_fixed, "documented, not served: %s" % sorted(flat - served_fixed)
assert served_fixed - flat <= {"/openapi.yml"}, "served, undocumented: %s" % sorted(served_fixed - flat - {"/openapi.yml"})

text = open("lp-api/openapi.yaml", encoding="utf-8").read()
body = text.split("\npaths:", 1)[1].split("\ncomponents:", 1)[0]
assert set(re.findall(r"^  (/\S*):$", body, re.M)) == documented, "openapi.yaml and openapi.json disagree"

print("   %d paths, all served, both spellings agree" % len(documented))
PY
note $?

step "API: openapi.json is not stale"
(cd lp-api && python3 -c "import yaml" 2>/dev/null \
  && python3 make-openapi-json.py --check \
  || echo "   skipped, PyYAML not installed"); note $?

step "App: abi.js is not stale"
# The page calls the contract by selector. If this file and the compiled contract ever disagree,
# every button on the page is calling something else.
(cd app && python3 make-abi-js.py --check); note $?

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

step "Landing: an unconfigured deployment refuses signups"
# A fresh interpreter, because what is being tested is what importing the production entry point
# does to the environment. This is how a live page came to answer 200 and lose the address:
# server.py imports dev_server for its handler, and dev_server set a writable path at import time.
python3 - <<'PY'
import os, sys
sys.path.insert(0, "landing")
for var in ("WAITLIST_FILE", "WAITLIST_WEBHOOK_URL", "VERCEL"):
    os.environ.pop(var, None)
import server  # noqa: F401  the production entry point
from api.waitlist import process

assert "WAITLIST_FILE" not in os.environ, "importing the server configured delivery by itself"
status, _ = process(b'{"email":"a@b.co"}')
assert status == 503, f"accepted a signup with nowhere to put it (got {status})"
print("   refuses with 503, and the import sets nothing")
PY
note $?

if [ "${1:-}" = "--fork" ]; then
  step "Solidity: fork integration tests"
  (cd lease-vault && ./fork-test.sh); note $?
fi

printf '\n'
[ "$fail" -eq 0 ] && printf '\033[1mall green\033[0m\n' || printf '\033[1msomething failed\033[0m\n'
exit $fail
