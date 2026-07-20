#!/usr/bin/env bash
# Self-hosted CI runners for Evidara on the Hetzner k3s cluster (ADR-0029).
#
# WHY: heavy CI jobs exhausted the GitHub-hosted Actions credit limit. We run the
# pools ourselves on the (near-idle) dedicated server via GitHub's Actions Runner
# Controller (ARC / gha-runner-scale-set). The two scale sets are named to match the
# repo Actions variables + every workflow's `runs-on:`:
#   LIGHT_RUNNER_SCALE_SET = evidara-light      (check-title, contract-validation, ...)
#   HEAVY_RUNNER_SCALE_SET = evidara-heavy-v2   (e2e/Playwright, DI heavy jobs)
# Docker/buildx image builds (runtime-images.yml) deliberately stay GitHub-hosted.
#
# The heavy pool runs a custom image (ghcr.io/philipplukas/evidara-runner-heavy) that
# bakes in Playwright's system libraries. It is built by runner-image.yml on push to
# main; the GHCR package must be public, since ARC pulls it without an imagePullSecret.
#
# Idempotent: `helm upgrade --install` throughout.
#
# ONE-TIME CREDENTIAL you must supply (I can't mint it for you):
#   Create a *classic* Personal Access Token with the `repo` scope
#   (https://github.com/settings/tokens/new?scopes=repo&description=evidara-arc-runners)
#   — or a GitHub App — then:
#
#   export GITHUB_RUNNER_PAT=ghp_xxx
#   bash infra/hetzner/deploy-runners.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_NS=arc-systems
RUNNERS_NS=arc-runners
CHART=oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
CONTROLLER_CHART=oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller
LIGHT_NAME=evidara-light
HEAVY_NAME=evidara-heavy-v2

: "${GITHUB_RUNNER_PAT:?Set GITHUB_RUNNER_PAT to a classic PAT with 'repo' scope (see header)}"

# The ARC charts are public on ghcr.io, but a leftover `credsStore: desktop` in
# ~/.docker/config.json makes helm shell out to a docker-credential-desktop helper
# that isn't installed. Point helm at a throwaway empty docker config so it pulls
# the public OCI charts anonymously.
# Declared and assigned separately (SC2155): `export X="$(cmd)"` always returns
# export's own status, so a failing mktemp would leave DOCKER_CONFIG empty and
# helm would fall back to the broken credsStore this line exists to avoid.
DOCKER_CONFIG="$(mktemp -d)"
export DOCKER_CONFIG

echo "==> 1/4 ARC controller (namespace ${CONTROLLER_NS})"
helm upgrade --install arc "${CONTROLLER_CHART}" \
  --namespace "${CONTROLLER_NS}" --create-namespace --wait

echo "==> 2/4 GitHub credential secret (namespace ${RUNNERS_NS})"
kubectl create namespace "${RUNNERS_NS}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${RUNNERS_NS}" create secret generic evidara-runner-github \
  --from-literal=github_token="${GITHUB_RUNNER_PAT}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> 3/4 LIGHT scale set (${LIGHT_NAME})"
helm upgrade --install "${LIGHT_NAME}" "${CHART}" \
  --namespace "${RUNNERS_NS}" \
  --set runnerScaleSetName="${LIGHT_NAME}" \
  -f "${SCRIPT_DIR}/runners/values-light.yaml" --wait

echo "==> 4/4 HEAVY scale set (${HEAVY_NAME})"
helm upgrade --install "${HEAVY_NAME}" "${CHART}" \
  --namespace "${RUNNERS_NS}" \
  --set runnerScaleSetName="${HEAVY_NAME}" \
  -f "${SCRIPT_DIR}/runners/values-heavy.yaml" --wait

echo
echo "Done. Verify listeners are up:"
echo "  kubectl -n ${CONTROLLER_NS} get pods"
echo "  kubectl -n ${RUNNERS_NS} get pods           # a *-listener pod per scale set"
echo "  gh api repos/philipplukas/evidara/actions/runners --jq '.runners[].name'"
echo
echo "Then re-run the required checks on an open PR (e.g. #504):"
echo "  gh pr checks 504 -R philipplukas/evidara"
