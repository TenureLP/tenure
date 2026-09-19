#!/usr/bin/env bash
# End-to-end smoke test against the live chain: free mode, then paywall mode.
cd "$(dirname "$0")/.." || exit 1
export LPVAL_SNAP_DB=/tmp/lpval_snap.sqlite LPVAL_DB=/tmp/lpval_pay.sqlite
TOKEN=${1:-2908278}

echo "### free mode"
python3 -m lpval serve --port 8402 >/tmp/lpval_free.log 2>&1 &
PID=$!
sleep 1.5
curl -s localhost:8402/health; echo
curl -s "localhost:8402/v1/position/$TOKEN/quote?term=7&haircut=0.15" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('value:', d['valueUSDG'])
print('feeRate:', {k:d['feeRate'].get(k) for k in ('available','source','lowConfidence','windowSeconds','feesUSDG','feeAprPercent','plausible','reason')})
print('quote:', {k:d['quote'].get(k) for k in ('suggestedSalePriceUSDG','expectedFeesOverTermUSDG','suggestedRentUSDG','eligibility')})
"
echo -n "unknown token -> "; curl -s -o /dev/null -w "%{http_code}\n" localhost:8402/v1/position/999999999
echo -n "bad route -> "; curl -s -o /dev/null -w "%{http_code}\n" localhost:8402/v1/nope
kill $PID; wait $PID 2>/dev/null

echo "### paywall mode"
LPVAL_PAY_TO=0x000000000000000000000000000000000000dEaD python3 -m lpval serve --port 8403 >/tmp/lpval_paid.log 2>&1 &
PID=$!
sleep 1.5
echo -n "no payment -> "; curl -s -w " [%{http_code}]\n" localhost:8403/v1/position/$TOKEN | tr -d '\n ' | cut -c1-260; echo
echo -n "fake tx -> "; curl -s -w " [%{http_code}]" -H "X-Payment-Tx: 0x$(printf 'ab%.0s' {1..32})" localhost:8403/v1/position/$TOKEN | python3 -c "import sys; s=sys.stdin.read(); print(s[s.find('reason')-1:].replace('\n',' '))"
echo -n "health stays free -> "; curl -s -o /dev/null -w "%{http_code}\n" localhost:8403/health
kill $PID; wait $PID 2>/dev/null
