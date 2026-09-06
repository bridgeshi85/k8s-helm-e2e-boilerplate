#!/usr/bin/env bash
set -euo pipefail

# Run one k6 load-test "batch" against TaskFlow and tag every k6 metric +
# every application span with the same batch id, so Grafana can filter both
# the k6 curves and the OTel traces down to this single run.
#
#   LOAD_TEST_ID  -> exported as env  (k6 setup() reads it, sends it as the
#                    X-Load-Test-ID request header -> OTel Baggage ->
#                    `test.load_test_id` span attribute)
#                 -> passed as `--tag load_test_id=...` (becomes a label on
#                    every k6_* metric written to Prometheus; k6's
#                    options.tags can't see setup()'s return value, so the
#                    id must come from outside the script)
#
# Usage:
#   ./scripts/run-loadtest.sh                        # random batch id
#   LOAD_TEST_ID=k6-my-run ./scripts/run-loadtest.sh # fixed batch id
#   BASE_URL=http://localhost:8080/api VUS=50 DURATION=3m ./scripts/run-loadtest.sh
#   ./scripts/run-loadtest.sh --quiet               # extra args go straight to k6
#
# Requires ./scripts/port-forward-all.sh running (Ingress :8080, Prometheus :9090).

SCRIPT="${SCRIPT:-k6_load_test/taskflow-loadtest.js}"

LOAD_TEST_ID="${LOAD_TEST_ID:-k6-$(date +%s)-$RANDOM}"

BASE_URL="${BASE_URL:-http://localhost:8080/api}"
PROM_RW_URL="${PROM_RW_URL:-http://localhost:9090/api/v1/write}"
PROM_RW_TREND_STATS="${PROM_RW_TREND_STATS:-p(50),p(90),p(95),p(99)}"

echo "================================================================"
echo " load_test_id : $LOAD_TEST_ID"
echo " script       : $SCRIPT"
echo " base url      : $BASE_URL"
echo " prometheus rw : $PROM_RW_URL"
echo "================================================================"
echo "In Grafana, filter by this batch:"
echo "  k6 metrics : {load_test_id=\"$LOAD_TEST_ID\"}"
echo "  Tempo      : { span.test.load_test_id = \"$LOAD_TEST_ID\" }"
echo "================================================================"

export LOAD_TEST_ID
export BASE_URL
export K6_PROMETHEUS_RW_SERVER_URL="$PROM_RW_URL"
export K6_PROMETHEUS_RW_TREND_STATS="$PROM_RW_TREND_STATS"

exec k6 run \
  --out experimental-prometheus-rw \
  --tag "load_test_id=$LOAD_TEST_ID" \
  "$@" \
  "$SCRIPT"
