# CI — Actions duration and runner tuning

Owner: Platform / DevEx  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
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
| GitHub-hosted | `ubuntu-latest` | **Release Readiness** (WIF + `gh` API); keep here unless OIDC is validated on self-hosted. **Dev-first orgs:** set repo variable **`RELEASE_READINESS_E2E_SMOKE_WORKFLOW`** to **`E2E Smoke Dev`** so the smoke gate matches your train — see [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) §2.1 and [Runtime stack §7](runtime-stack.md#7-release-readiness-go-no-go-operation). |

If self-hosted queues starve PRs, **scale runner count** or **split labels** (e.g. dedicated Playwright vs Docker-heavy) instead of moving every job to one pool.

## Related

- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) — Release Readiness strict gate
- [Scripts README](../../scripts/README.md) — `analyze_github_actions_queue.py` table entry
