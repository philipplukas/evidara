# CI — Actions duration and runner tuning

Owner: Platform / DevEx  
Last reviewed: 2026-04-13
Last verified: 2026-04-13
Applies to: GitHub Actions queue vs run time; org vars `LIGHT_RUNNER_RUNS_ON_JSON`, `HEAVY_RUNNER_RUNS_ON_JSON`

## Why measure first

Several workflows already honor **self-hosted** labels via org/repo variables (see [legal-search workflow](../../.github/workflows/legal-search.yml), [e2e-smoke-dev](../../.github/workflows/e2e-smoke-dev.yml), [terraform](../../.github/workflows/terraform.yml)). Before adding runners or changing labels, **quantify** which workflows dominate queue or wall time.

## Pull median / p95 style metrics

From repo root, with [`gh`](https://cli.github.com/) authenticated:

```bash
./scripts/analyze_github_actions_queue.py -L 200
./scripts/analyze_github_actions_queue.py -w "Legal Search" -w "Terraform" -w "Document Intelligence" -L 100 --aggregate-jobs
./scripts/analyze_github_actions_queue.py --per-job --workflow "Legal Search" -L 20
./scripts/analyze_github_actions_queue.py --csv > /tmp/actions-queue.csv
```

See `scripts/analyze_github_actions_queue.py --help` for filters (`--repo`, `--branch`, etc.).

## Runner policy (this repo)

| Pool | Org variable | Typical jobs |
|------|----------------|--------------|
| Light | `LIGHT_RUNNER_SCALE_SET` | PR title, path detection, docs/contracts, runtime config checks, Cloud Run/Databricks deploy orchestration, Release Readiness (WIF + `gh` API). The light pool must allow `curl`, `sudo`, and apt package installation when workflows bootstrap missing tools. **Dev-first orgs:** set **`RELEASE_READINESS_GITHUB_ENVIRONMENT`** = **`dev`**, **`RELEASE_READINESS_E2E_SMOKE_WORKFLOW`** = **`E2E Smoke Dev`**, and ensure GitHub **Environment `dev`** has the same OIDC secrets as E2E Smoke Dev — see [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) §2.1 and [Runtime stack §7](runtime-stack.md#7-release-readiness-go-no-go-operation). |
| Heavy | `HEAVY_RUNNER_SCALE_SET` | Docker/image builds, fuller document-intelligence checks, Playwright / interaction-flow, e2e smokes. |
| GitHub-hosted | `ubuntu-latest` | Emergency fallback only for jobs that cannot yet run on the self-hosted pools. |

Current exception:

- Jobs that bootstrap generic Node or Python via `actions/setup-node` / `actions/setup-python` may need `ubuntu-latest` while the self-hosted ARC pools are being hardened for those toolchains.
- Use `.github/workflows/runner-pool-smoke.yml` for non-PR-blocking light/heavy pool verification while the bridge period is still active.

## Bridge policy while Hetzner K8s runners are being installed

MacConfig owns the Hetzner Kubernetes cluster and the cluster-scoped runner platform objects. Until that platform work lands, this repo uses a bridge policy:

- Keep generic language bootstrap jobs on `ubuntu-latest`.
- Keep runner-native jobs on the existing self-hosted labels only when they do not depend on `actions/setup-node` or `actions/setup-python`.
- After the Kubernetes runner pools exist, switch the org variables instead of hardcoding new labels across many workflows.

### Current GitHub-hosted bridge inventory

These workflows still intentionally use `ubuntu-latest` today because they rely on `actions/setup-node` and/or `actions/setup-python` and have not yet been moved behind the light/heavy pool variables:

| Workflow | Job | Reason |
|------|------|------|
| `legal-search.yml` | `api`, `frontend`, `interaction-flow-evidence` | `setup-node` Node 22 |
| `platform-control.yml` | `check` | `setup-python` + `setup-node` |
| `evidara-cli.yml` | `evidara-cli` | `setup-python` |
| `evidara-cli-remote-smoke.yml` | `remote-smoke` | `setup-python` |
| `scraping-qa.yml` | `scraping-qa` | `setup-python` |
| `interaction-flow-staging-evidence.yml` | `interaction-flow-staging-evidence` | `setup-node` + Playwright |

### Target Hetzner K8s label policy

Once MacConfig publishes Kubernetes-managed GitHub Actions runners for Evidara, point the org variables at label sets in this shape:

| Pool | Target label JSON | Notes |
|------|------|------|
| Light | `["self-hosted","linux","x64","evidara","light","k8s"]` | Generic Node/Python CI and smaller validation jobs |
| Heavy | `["self-hosted","linux","x64","evidara","heavy","k8s"]` | Browser and higher-resource validation jobs |

Evidara should not own the runner controller, CRDs, or cluster RBAC in `k8s/gitops/`; those belong in MacConfig with the cluster platform setup.

## Post-cutover validation checklist

After the K8s runner pools are live and the org variables are updated:

1. Re-run the workflows listed in the bridge inventory above on the new labels.
2. Verify `setup-node` Node 22 and `setup-python` Python 3.12/3.11 complete without bootstrap errors.
3. Compare queue time and wall time against:
   - the legacy Hetzner NixOS VM runners
   - `ubuntu-latest`
4. Decide which jobs remain on:
   - K8s light
   - K8s heavy
   - GitHub-hosted
   - any specialized build pool for Docker-heavy or privileged jobs
5. Only after that decision, move any remaining bridge workflows back behind `LIGHT_RUNNER_RUNS_ON_JSON` / `HEAVY_RUNNER_RUNS_ON_JSON`.

If self-hosted queues starve PRs, **scale runner count** or **split labels** (e.g. dedicated Playwright vs Docker-heavy) instead of moving every job to one pool.

## Runner reliability checklist

Use this when the ARC / self-hosted pools drift, queue jobs, or re-register with unexpected labels.

### Current stable target

- Light pool should resolve to `["self-hosted","linux","x64","evidara","light","k8s"]`.
- Heavy pool should resolve to `["self-hosted","linux","x64","evidara","heavy","k8s"]`.
- `runner-bootstrap-preflight.yml` is the canonical bootstrap smoke for both pools.
- `runner-pool-smoke.yml` is the recurring light/heavy health check.
- `runtime-images.yml` should stay separate from the generic light/heavy pools until a Docker-capable runner class is proven stable.

### Likely failure modes seen recently

- Label drift after ARC pod or runner rotation, including runners coming back with empty or partial label sets.
- Ghost-busy or stale registration state, where GitHub shows runners online but jobs still do not dequeue reliably.
- Docker/buildx readiness gaps on the heavy pool, especially for repeated `docker/setup-buildx-action` + `docker/build-push-action` jobs.
- Terraform wrapper bootstrap failures on self-hosted Linux when `hashicorp/setup-terraform` assumes a Node wrapper that is not available.

### Remediation checklist

1. Confirm both pools are online and advertising the full target label set.
2. Verify light-pool jobs can bootstrap Node 22, Python 3.11, `git`, `curl`, and `unzip` with `runner-bootstrap-preflight.yml`, and can run Release Readiness' GitHub CLI bootstrap when `gh` is absent.
3. Verify heavy-pool jobs can launch Chromium and complete the Playwright smoke path with `runner-bootstrap-preflight.yml` and `runner-pool-smoke.yml`.
4. Verify Docker/buildx availability before routing image jobs to heavy. If Docker is not guaranteed, keep `runtime-images.yml` off that pool.
5. Keep `terraform.yml` on a bootstrap path that does not depend on the Terraform wrapper assuming Node is present on the runner.
6. If labels disappear on rotation, fix the runner class / scale-set registration before changing workflow selectors again.
7. Do not use required-check workarounds as a substitute for runner health; they only hide queueing problems.

### Verification plan

Run these checks after any runner pool change or ARC recycle:

```bash
gh workflow run runner-bootstrap-preflight.yml \
  -f runner_scale_set='evidara-light' \
  -f node_version='22' \
  -f python_version='3.11' \
  -f frontend_playwright_smoke=false

gh workflow run runner-bootstrap-preflight.yml \
  -f runner_scale_set='evidara-heavy' \
  -f node_version='22' \
  -f python_version='3.11' \
  -f frontend_playwright_smoke=true

gh workflow run runner-pool-smoke.yml
```

Pass criteria:

- both bootstrap workflows leave `queued` state and start promptly
- light pool completes the Node / Python bootstrap steps without wrapper or missing-binary errors
- heavy pool completes the browser smoke path and does not regress to label-less or busy-stuck runners
- `runtime-images.yml` only moves back onto the self-hosted path after the pool can sustain Docker/buildx builds repeatedly

### Related issues

- `TAR-70` — gate policy hardening and required-check alignment
- `TAR-214` — release evidence refresh, including runner-facing verification artifacts
- `TAR-160` — GA sign-off, once the pools are stable enough to trust for release evidence
- `runner-trust-verification-checklist.md` — copy-paste verification, incident response, and cutover readiness matrix

## Related

- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) — Release Readiness strict gate
- [Scripts README](../../scripts/README.md) — `analyze_github_actions_queue.py` table entry
