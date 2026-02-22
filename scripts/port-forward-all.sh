#!/usr/bin/env bash
set -euo pipefail

# One-command port-forward for local dev
# - Ingress NGINX:  http://localhost:8080
# - Grafana:        http://localhost:3000
# - Prometheus:     http://localhost:9090

INGRESS_NS="${INGRESS_NS:-ingress-nginx}"
OBS_NS="${OBS_NS:-observability}"

pick_service() {
  local ns="$1"
  shift
  local candidates=("$@")

  for name in "${candidates[@]}"; do
    if kubectl get svc -n "$ns" "$name" >/dev/null 2>&1; then
      echo "$name"
      return 0
    fi
  done

  return 1
}

start_pf() {
  local ns="$1"
  local svc="$2"
  local local_port="$3"
  local remote_port="$4"

  echo "[port-forward] $ns/$svc ${local_port}:${remote_port}"
  kubectl port-forward -n "$ns" "svc/$svc" "${local_port}:${remote_port}" \
    >/tmp/pf-${ns}-${svc}-${local_port}.log 2>&1 &
  PIDS+=("$!")
}

PIDS=()

cleanup() {
  echo ""
  echo "Stopping all port-forward processes..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
}
trap cleanup EXIT INT TERM

INGRESS_SVC="${INGRESS_SVC:-$(pick_service "$INGRESS_NS" ingress-nginx-controller)}"
GRAFANA_SVC="${GRAFANA_SVC:-$(pick_service "$OBS_NS" observability-grafana kube-prometheus-stack-grafana)}"
PROM_SVC="${PROM_SVC:-$(pick_service "$OBS_NS" observability-kube-prometh-prometheus kube-prometheus-stack-prometheus prometheus-operated)}"

if [[ -z "${INGRESS_SVC:-}" || -z "${GRAFANA_SVC:-}" || -z "${PROM_SVC:-}" ]]; then
  echo "Failed to auto-detect one or more services."
  echo "Check service names with: kubectl get svc -A"
  echo "You can override via env vars: INGRESS_SVC, GRAFANA_SVC, PROM_SVC"
  exit 1
fi

start_pf "$INGRESS_NS" "$INGRESS_SVC" 8080 80
start_pf "$OBS_NS" "$GRAFANA_SVC" 3000 80
start_pf "$OBS_NS" "$PROM_SVC" 9090 9090

echo ""
echo "Ready:"
echo "- Ingress:    http://localhost:8080"
echo "- Grafana:    http://localhost:3000"
echo "- Prometheus: http://localhost:9090"
echo ""
echo "Press Ctrl+C to stop all forwards."

wait
