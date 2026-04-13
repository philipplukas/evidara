# Runner trust verification checklist

Owner: Platform / DevEx  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: ARC / self-hosted runner trust, light/heavy pool verification, release-cutover readiness

Use this page when you need a copy-paste operator checklist that proves the runner pools can actually take work, not just show up online in GitHub.

Related:

- [CI actions duration and runner tuning](ci-actions-duration-metrics.md)
- [GA operator board](ga-operator-board.md)
- [TAR-70 gate policy hardening](tar-70-gate-policy-hardening.md)

## 1. What "good" looks like

The runner pools are trustworthy when all of these are true:

- GitHub shows at least one online light runner with the full label set.
- GitHub shows at least one online heavy runner with the full label set.
- `runner-bootstrap-preflight.yml` starts promptly on both pools.
- Light bootstrap proves Node 22 and Python 3.11.
- Heavy bootstrap proves Node 22, Python 3.11, and the Playwright browser smoke.
- `runner-pool-smoke.yml` completes without queue stalls or label drift.
- Jobs stop being queued for runner reasons and start failing only on actual code or config issues.

Target labels:

- Light: `["self-hosted","linux","x64","evidara","light","k8s"]`
- Heavy: `["self-hosted","linux","x64","evidara","heavy","k8s"]`

## 2. Copy-paste verification

Run these from repo root.

### 2.1 Inspect live registration first

```bash
gh api repos/philipplukas/evidara/actions/runners \
  --jq '.runners[] | {name,status,busy,labels:[.labels[].name]}'
```

Pass:

- the expected light and heavy runners are `online`
- `busy` is `false` on the idle pool you are trying to verify
- the label arrays include the full target label set

Fail:

- any runner is `offline`
- labels are missing or empty
- GitHub shows runners online but jobs are not dequeuing

### 2.2 Verify the light pool

```bash
gh workflow run runner-bootstrap-preflight.yml \
  -f runner_scale_set='evidara-light' \
  -f node_version='22' \
  -f python_version='3.11' \
  -f frontend_playwright_smoke=false
```

Then watch the newest dispatch:

```bash
gh run list \
  --workflow "Runner Bootstrap Preflight" \
  --event workflow_dispatch \
  --limit 1 \
  --json databaseId,status,conclusion,displayTitle,createdAt
```

Pass:

- the workflow leaves the queue and starts promptly
- `Snapshot runner` passes
- `Setup Node` and `Setup Python` pass
- summary shows Node 22 and Python 3.11

### 2.3 Verify the heavy pool

```bash
gh workflow run runner-bootstrap-preflight.yml \
  -f runner_scale_set='evidara-heavy' \
  -f node_version='22' \
  -f python_version='3.11' \
  -f frontend_playwright_smoke=true
```

Pass:

- the workflow leaves the queue and starts promptly
- `Install Playwright Chromium` passes
- `Verify Playwright browser smoke` passes
- summary shows the heavy pool actually handled browser bootstrap

### 2.4 Run the recurring smoke

```bash
gh workflow run runner-pool-smoke.yml
```

Pass:

- both reusable jobs complete
- light and heavy pools remain labeled after rotation
- no runner sits in a ghost-busy state after the smoke completes

## 3. Cutover readiness matrix

| Area | Ready | Not ready |
|------|-------|-----------|
| Light bootstrap | Node 22 and Python 3.11 start on first try | missing binaries, wrapper failures, or queue stalls |
| Heavy browser smoke | Chromium launches and exits cleanly | Playwright install failures or label drift |
| Runner registration | online and labeled | online but unlabeled, offline, or ghost-busy |
| Image jobs | only routed when Docker/buildx is known good | routed before Docker-capable runner trust is proven |
| Terraform jobs | run without wrapper/bootstrap surprises | wrapper assumes Node or other missing runtime |

## 4. Incident response

| Symptom | First check | Likely cause | Immediate operator move |
|--------|-------------|--------------|-------------------------|
| Jobs stay queued on a runner workflow | `gh api .../actions/runners` | label drift or runner offline | re-check labels, then recycle the runner registration |
| Runner shows online but jobs do not start | `gh run list` and runner `busy` state | ghost-busy or stale registration | recycle the runner pod or scale-set registration before changing selectors |
| Light bootstrap fails on Node/Python | workflow log around `actions/setup-node` / `actions/setup-python` | missing runtime bootstrap on the light class | keep the pool on the current label contract and fix the image/bootstrap path |
| Heavy smoke fails at browser install | `Install Playwright Chromium` / `Verify Playwright browser smoke` | heavy pool not yet stable for browser workloads | keep browser jobs on the proven heavy pool only; do not widen scope |
| Image jobs fail at Docker/buildx | `docker/setup-buildx-action` / `docker buildx build` | Docker-capable runner class is not stable yet | keep `runtime-images.yml` off this pool until repeated passes hold |
| Terraform jobs fail in wrapper bootstrap | `hashicorp/setup-terraform` step | wrapper assumed Node on self-hosted runner | keep wrapper disabled on self-hosted paths that need it |

## 5. Exit criteria for TAR-238

`TAR-238` is healthy enough to trust when:

- both pools stay online with the full label contract across rotation
- `runner-bootstrap-preflight.yml` starts and passes on light and heavy
- `runner-pool-smoke.yml` passes after a recycle
- queued jobs are due to actual workload, not runner registration drift
- the next release evidence run can rely on the pool without a manual recovery step
