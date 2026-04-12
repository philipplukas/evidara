#!/usr/bin/env bash
# Render k8s/gitops Kustomize roots (requires kubectl with built-in kustomize).
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v kubectl >/dev/null 2>&1; then
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    echo "kubectl is required in GitHub Actions to validate k8s/gitops."
    exit 1
  fi
  echo "kubectl not found; skipping k8s/gitops kustomize validation."
  exit 0
fi
for dir in "${root}/k8s/gitops/dev" "${root}/k8s/gitops/staging" "${root}/k8s/gitops/prod"; do
  echo "kubectl kustomize ${dir#"${root}/"}"
  kubectl kustomize "$dir" >/dev/null
done
echo "OK: all k8s/gitops kustomizations render."
