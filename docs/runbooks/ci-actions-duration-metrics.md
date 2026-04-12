# CI — Actions duration and runner tuning

Owner: Platform / DevEx  
Last reviewed: 2026-04-12  
Last verified: 2026-04-12  
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
| Light | `LIGHT_RUNNER_RUNS_ON_JSON` | fmt, unit tests, npm `check`, Terraform fmt/plan when pointed here |
| Heavy | `HEAVY_RUNNER_RUNS_ON_JSON` | Playwright / interaction-flow, e2e smokes, multi-arch image builds |
| GitHub-hosted | `ubuntu-latest` | **Release Readiness** (WIF + `gh` API); keep here unless OIDC is validated on self-hosted. **Dev-first orgs:** set **`RELEASE_READINESS_GITHUB_ENVIRONMENT`** = **`dev`**, **`RELEASE_READINESS_E2E_SMOKE_WORKFLOW`** = **`E2E Smoke Dev`**, and ensure GitHub **Environment `dev`** has the same OIDC secrets as E2E Smoke Dev — see [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) §2.1 and [Runtime stack §7](runtime-stack.md#7-release-readiness-go-no-go-operation). |

Current exception:

- Jobs that depend on `actions/setup-node`, `actions/setup-python`, or mixed Node/Python bootstrap may still need `ubuntu-latest` while the self-hosted bridge path is being proven incrementally.
- Python-only jobs can use `uv python install` as the bridge bootstrap on the legacy self-hosted pool before the Ubuntu-compatible runner target exists.
- Use `.github/workflows/runner-pool-smoke.yml` for non-PR-blocking light/heavy pool verification while the bridge period is still active.

## Bridge policy while Hetzner K8s runners are being installed

MacConfig owns the Hetzner Kubernetes cluster and the cluster-scoped runner platform objects. Until that platform work lands, this repo uses a bridge policy:

- Migrate the smallest proven light-pool jobs back behind `LIGHT_RUNNER_RUNS_ON_JSON` first.
- Keep larger mixed-toolchain or browser-heavy bootstrap jobs on `ubuntu-latest` until their pool proof exists.
- Keep runner-native jobs on the existing self-hosted labels only when they do not depend on `actions/setup-node` or `actions/setup-python`.
- After the Kubernetes runner pools exist, switch the org variables instead of hardcoding new labels across many workflows.

### Current GitHub-hosted bridge inventory

These workflows intentionally use `ubuntu-latest` today because they rely on `actions/setup-node` and/or `actions/setup-python`:

| Workflow | Job | Reason |
|------|------|------|
| `legal-search.yml` | `api`, `frontend`, `interaction-flow-evidence` | `setup-node` Node 22 |
| `docs-and-contracts.yml` | `contract-validation` | `setup-python` + `setup-node` |
| `platform-control.yml` | `check` | `setup-python` + `setup-node` |
| `document-intelligence.yml` | `document-intelligence-check` | `setup-python` + `setup-node` |
| `evidara-cli-remote-smoke.yml` | `remote-smoke` | `setup-python` |
| `interaction-flow-staging-evidence.yml` | `interaction-flow-staging-evidence` | `setup-node` + Playwright |

As of 2026-04-12, `evidara-cli.yml` and `scraping-qa.yml` moved back to the light runner pool after `runner-pool-smoke.yml` landed and proved the repo's `uv`-based Python bootstrap on the bridge self-hosted labels.

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

## Related

- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) — Release Readiness strict gate
- [Scripts README](../../scripts/README.md) — `analyze_github_actions_queue.py` table entry
