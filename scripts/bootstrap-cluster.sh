#!/usr/bin/env bash
# Installs the platform on a fresh k3s node: secrets, observability charts, Argo CD.
# Re-running it is safe; existing secrets are left alone.
set -euo pipefail

KPS_VERSION=91.9.0
LOKI_VERSION=18.13.8
TEMPO_VERSION=3.1.0
OTEL_VERSION=0.175.0
ARGOCD_VERSION=v3.5.3

cd "$(dirname "$0")/.."

ensure_ns() {
  kubectl create namespace "$1" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
}

ensure_secret() {
  local ns=$1 name=$2
  shift 2
  if kubectl -n "$ns" get secret "$name" >/dev/null 2>&1; then
    echo "secret $ns/$name exists, keeping it"
  else
    kubectl -n "$ns" create secret generic "$name" "$@"
  fi
}

for ns in shop observability argocd; do ensure_ns "$ns"; done

ensure_secret shop redis-auth --from-literal=password="$(openssl rand -hex 24)"
ensure_secret observability grafana-admin \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$(openssl rand -base64 18)"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo add grafana-community https://grafana-community.github.io/helm-charts >/dev/null
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null
helm repo update >/dev/null

install() {
  local release=$1 chart=$2 version=$3
  echo "--> $release ($chart $version)"
  helm upgrade --install "$release" "$chart" \
    --namespace observability \
    --version "$version" \
    --values "deploy/helm/$release.yaml" \
    --wait --timeout 10m
}

install kube-prometheus-stack prometheus-community/kube-prometheus-stack "$KPS_VERSION"
install loki grafana-community/loki "$LOKI_VERSION"
install tempo grafana-community/tempo "$TEMPO_VERSION"
install otel-collector open-telemetry/opentelemetry-collector "$OTEL_VERSION"

echo "--> argo cd $ARGOCD_VERSION"
kubectl apply -n argocd --server-side --force-conflicts \
  -f "https://raw.githubusercontent.com/argoproj/argo-cd/$ARGOCD_VERSION/manifests/install.yaml"
kubectl -n argocd rollout status deploy/argocd-server --timeout=5m
kubectl apply -f deploy/argocd/shop.yaml

echo
echo "grafana password: kubectl -n observability get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d"
