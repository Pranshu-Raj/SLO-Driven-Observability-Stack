#!/usr/bin/env bash
# Places one order through the frontend and waits for the worker to fulfil it.
# usage: scripts/smoke.sh [base-url]
set -euo pipefail

BASE=${1:-http://localhost:8080}
RID="smoke-$(date +%s)"

fail() { echo "FAIL: $*" >&2; exit 1; }

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/healthz")
[[ $code == 200 ]] || fail "healthz returned $code"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/products")
[[ $code == 200 ]] || fail "products returned $code"

body=$(curl -s -w '\n%{http_code}' -H "x-request-id: $RID" -H 'content-type: application/json' \
  -d '{"product_id":"huila","quantity":1}' "$BASE/checkout")
code=${body##*$'\n'}
[[ $code == 202 ]] || fail "checkout returned $code: ${body%$'\n'*}"
order_id=$(sed -E 's/.*"id":"([0-9a-f]+)".*/\1/' <<<"${body%$'\n'*}")

for _ in $(seq 1 20); do
  if curl -s "$BASE/orders/$order_id" | grep -q '"status":"fulfilled"'; then
    echo "ok: order $order_id fulfilled (request id $RID)"
    exit 0
  fi
  sleep 0.5
done
fail "order $order_id not fulfilled after 10s (request id $RID)"
