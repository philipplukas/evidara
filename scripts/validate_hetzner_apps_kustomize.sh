#!/usr/bin/env bash
# Render the one Kustomize root that actually deploys: `infra/hetzner/apps`.
#
# Replaces `validate_k8s_gitops_kustomize.sh` (ADR-0055). That gate rendered
# `k8s/gitops/{dev,staging,prod}` and printed "OK: all ... render" — but the prod
# overlay was `resources: []`, so it reported success over an overlay that
# rendered NOTHING, for the environment that mattered most. ADR-0051: a gate that
# cannot fail is not a gate.
#
# So this one asserts content, not just exit status. A kustomization that renders
# empty, or that loses a workload, fails here.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${root}/infra/hetzner/apps"

if ! command -v kubectl >/dev/null 2>&1; then
  # Unlike the gate this replaces, the local skip is loud. A silent "skipping"
  # line scrolls past and reads as a pass in a terminal full of green.
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    echo "FAIL: kubectl is required in GitHub Actions to validate infra/hetzner/apps." >&2
    exit 1
  fi
  echo "DID-NOT-RUN: kubectl not found, so infra/hetzner/apps was NOT validated." >&2
  echo "             Install kubectl to run this gate locally; CI runs it unconditionally." >&2
  exit 0
fi

echo "kubectl kustomize infra/hetzner/apps"
rendered="$(kubectl kustomize "$target")"

if [[ -z "${rendered//[[:space:]]/}" ]]; then
  echo "FAIL: infra/hetzner/apps rendered empty." >&2
  exit 1
fi

# Every workload this cluster runs must appear. Losing one from `resources:` is a
# silent, valid-YAML mistake: the render still succeeds and the workload simply
# stops being deployed. Under Argo CD with `prune: false` it would not even be
# deleted — it would just stop being updated, which is the least visible failure
# available.
expected_names=(
  platform-control-api
  platform-control-admin
  legal-search-api
  legal-search-frontend
  di-consumer
  document-service
  platform-control-migrate
  # Joined the kustomization in #884. Until then it was the one workload in the
  # namespace no declarative config governed, and this list not naming it is part
  # of why that went unnoticed for as long as it did.
  marketing
  # The two CronJobs, added in #1038. Both were in `resources:` and neither was in
  # this list, so dropping either from the kustomization rendered valid YAML, kept
  # this check green, and silently stopped the job running — the precise failure
  # the comment above this list describes, sitting inside the guard that describes
  # it. A scheduled job is the worst case for that: nothing errors, nothing is
  # deleted under `prune: false`, and the only symptom is work that quietly stops
  # happening. Which is how 116 documents went unreclaimed for nine days.
  platform-control-retention-sweep
  platform-control-processing-reclaim
)

# The marketing Ingress is the other half of #884 and the half nothing checked: the
# Deployment and Service were applied, the Ingress never was, and a healthy pod with
# no route reads as green in every workload-shaped signal there is. Assert the route
# renders, not just the workload.
if ! grep -q '^[[:space:]]*name: marketing-tls$' <<<"$rendered"; then
  echo "FAIL: infra/hetzner/apps renders the marketing workload without its Ingress." >&2
  echo "      A Deployment with no Ingress is perfectly healthy and reaches nobody —" >&2
  echo "      which is exactly how evidara.veyo.dev served no one for the life of #884." >&2
  exit 1
fi
missing=()
for name in "${expected_names[@]}"; do
  grep -qE "^[[:space:]]*name: ${name}$" <<<"$rendered" || missing+=("$name")
done

if (( ${#missing[@]} > 0 )); then
  echo "FAIL: infra/hetzner/apps renders without: ${missing[*]}" >&2
  echo "      If a workload was intentionally removed, update expected_names in this script" >&2
  echo "      in the same commit — so the removal is a decision, not a diff nobody saw." >&2
  exit 1
fi

# The migrate Job must carry its Argo CD PreSync hook. Without it Argo applies the
# Job alongside the workloads instead of before them, and a platform-control that
# expects a migration can roll ahead of the migration itself (ADR-0055).
if ! grep -q 'argocd.argoproj.io/hook: PreSync' <<<"$rendered"; then
  echo "FAIL: the migrate Job renders without its 'argocd.argoproj.io/hook: PreSync' annotation." >&2
  echo "      Argo CD would then roll the API without waiting for Alembic to finish." >&2
  exit 1
fi

echo "OK: infra/hetzner/apps renders ${#expected_names[@]} workloads, migrate Job hooked PreSync."
