# ARC Runner Migration Matrix

This matrix defines the first migration wave from the old Hetzner host runners to
the new ARC-managed Kubernetes pools.

Before any destructive rebuild or runner retirement, preserve the legacy host
state with [Hetzner runner secret capture](../runbooks/hetzner-runner-secret-capture.md)
and its [checklist](../runbooks/hetzner-runner-secret-capture-checklist.md).

Target label contract:

- `LIGHT_RUNNER_RUNS_ON_JSON='["self-hosted","linux","x64","evidara","light","k8s"]'`
- `HEAVY_RUNNER_RUNS_ON_JSON='["self-hosted","linux","x64","evidara","heavy","k8s"]'`

## Move To ARC Light First

These are the best first targets once the new light pool is healthy.

- [`runner-bootstrap-preflight.yml`](../../.github/workflows/runner-bootstrap-preflight.yml)
  This is the canonical smoke for `actions/setup-node` and `actions/setup-python`.
- [`runner-pool-smoke.yml`](../../.github/workflows/runner-pool-smoke.yml)
  Keep this as the recurring validation entrypoint for both pools.
- [`document-intelligence.yml`](../../.github/workflows/document-intelligence.yml)
  `document-intelligence-runtime-check` already targets the light runner variable.
- [`terraform.yml`](../../.github/workflows/terraform.yml)
  Light-weight Terraform fmt/plan/apply jobs are good early candidates.
- [`terraform-databricks.yml`](../../.github/workflows/terraform-databricks.yml)
  Similar pattern to the Terraform runtime stack, with light-runner usage today.
- [`pr-title.yml`](../../.github/workflows/pr-title.yml)
  Cheap policy/validation work on the light pool is low risk.

## Move To ARC Heavy After Validation

These should wait until the heavy pool has proven Playwright/integration stability.

- [`runner-pool-smoke.yml`](../../.github/workflows/runner-pool-smoke.yml)
  Heavy smoke should prove browser setup and Playwright readiness first.
- [`e2e-smoke-dev.yml`](../../.github/workflows/e2e-smoke-dev.yml)
  End-to-end smoke belongs on the heavy pool after the browser/runtime path is stable.
- [`e2e-smoke-staging.yml`](../../.github/workflows/e2e-smoke-staging.yml)
  Same as dev: migrate after heavy validation passes repeatedly.

## Keep Off Cluster For Now

These still assume Docker-heavy, buildx, or privileged container-build behavior.

- [`runtime-images.yml`](../../.github/workflows/runtime-images.yml)
  Uses `docker/setup-buildx-action` and `docker/build-push-action` repeatedly on
  the heavy runner path.

Keep these on the old path or another validated runner class until a dedicated
container-build design exists.

## Already GitHub-Hosted / No Immediate Action

These are already intentionally kept off the old Hetzner runner path for
`setup-node` / `setup-python` stability.

- [`platform-control.yml`](../../.github/workflows/platform-control.yml)
- [`document-intelligence.yml`](../../.github/workflows/document-intelligence.yml)
- [`docs-and-contracts.yml`](../../.github/workflows/docs-and-contracts.yml)
- [`legal-search.yml`](../../.github/workflows/legal-search.yml)
- [`scraping-qa.yml`](../../.github/workflows/scraping-qa.yml)
- [`evidara-cli.yml`](../../.github/workflows/evidara-cli.yml)
- [`evidara-cli-remote-smoke.yml`](../../.github/workflows/evidara-cli-remote-smoke.yml)
- [`interaction-flow-staging-evidence.yml`](../../.github/workflows/interaction-flow-staging-evidence.yml)

No migration is required for these until you intentionally decide to move them
from GitHub-hosted Linux to the new Kubernetes pools.

## Recommended Order

1. Bring up the ARC light pool and pass [`runner-bootstrap-preflight.yml`](../../.github/workflows/runner-bootstrap-preflight.yml).
2. Pass [`runner-pool-smoke.yml`](../../.github/workflows/runner-pool-smoke.yml) for the light pool.
3. Move light-runner workflows already using `LIGHT_RUNNER_RUNS_ON_JSON`.
4. Validate the heavy pool with the Playwright-enabled smoke path.
5. Move heavy integration workflows.
6. Keep `runtime-images.yml` and similar Docker/buildx jobs separate until a new
   dedicated runner class is proven.
