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
python3 -m compileall -q lp-api/lpval landing/dev_server.py landing/server.py \
  landing/read_waitlist.py app/server.py docs-site/server.py >/dev/null; note $?

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
routes = (server._ROUTE, server._OWNER_ROUTE)
for path in templated:
    concrete = path.replace("{tokenId}", "2908254").replace("{address}", "0x" + "ab" * 20)
    assert any(r.match(concrete) for r in routes), "documented, not served: %s" % path

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

step "App: the codec that encodes every transaction agrees with cast"
# Node is only needed here, and is not a dependency of anything that ships. Skipped rather than
# failed when it is absent, the same way the PyYAML check is.
NODE=$(command -v node || ls -d $HOME/.nvm/versions/node/*/bin/node 2>/dev/null | tail -1)
if [ -n "$NODE" ]; then
  "$NODE" --test app/test/*.test.js >/tmp/tenure-app-tests.log 2>&1
  r=$?; grep -E '^# (pass|fail)' /tmp/tenure-app-tests.log | tr '
' ' ' | sed 's/^/   /'; echo
  [ $r -ne 0 ] && grep -E '^not ok' /tmp/tenure-app-tests.log | sed 's/^/   /'
  note $r
else
  echo '   skipped, no node on this machine'; note 0
fi

step "App: abi.js is not stale"
# The page calls the contract by selector. If this file and the compiled contract ever disagree,
# every button on the page is calling something else.
(cd app && python3 make-abi-js.py --check); note $?

step "Landing and docs: the icons and the app screens are the same set on both sites"
# The icons are generated from one table into both; the screens are copied. Either drifting apart
# means one site shows the product as it was and the other as it is.
(cd landing && python3 make-icons.py --check)   && diff -rq landing/assets/shots docs-site/public/shots >/dev/null   && echo "   icons generated, $(ls landing/assets/shots | wc -l) screens identical"; note $?

step "Landing and app: each server serves its pages and nothing beside them"
python3 check-servers.py; note $?


step "Docs: the site builds, and no page links to one that does not exist"
# VitePress refuses to build with a dead internal link, which is the check worth having here.
if [ -n "$NODE" ] && [ -d docs-site/node_modules ]; then
  (cd docs-site && PATH="$(dirname "$NODE"):$PATH" npm run build >/tmp/tenure-docs-build.log 2>&1)
  r=$?; [ $r -ne 0 ] && tail -20 /tmp/tenure-docs-build.log | sed 's/^/   /'
  note $r
else
  echo '   skipped, run npm ci in docs-site first'; note 0
fi

if [ "${1:-}" = "--fork" ]; then
  step "Solidity: fork integration tests"
  (cd lease-vault && ./fork-test.sh); note $?
fi

printf '\n'
[ "$fail" -eq 0 ] && printf '\033[1mall green\033[0m\n' || printf '\033[1msomething failed\033[0m\n'
exit $fail
