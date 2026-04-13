# TAR-238 runner recycle checklist

Owner: Platform / DevEx  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: ARC runner-registration drift, queued self-hosted jobs, stalled light/heavy pool validation

## Purpose

Use this checklist when GitHub shows self-hosted runners online but queued jobs still do
not start, or when runner labels drift after ARC rotation. This is the operator follow-up
for the 2026-04-13 incident where `E2E Smoke Dev` and `Runner Bootstrap Preflight`
stayed queued despite an idle heavy runner.

Primary references:

- [Runner trust verification checklist](runner-trust-verification-checklist.md)
- [CI actions duration and runner tuning](ci-actions-duration-metrics.md)
- [TAR-70 gate policy hardening](tar-70-gate-policy-hardening.md)

## Incident shape

Treat the runner layer as unhealthy when any of these are true:

- a self-hosted workflow stays `queued` even though a matching runner looks idle
- the light pool comes back with `labels: []`
- the heavy pool looks online but jobs do not dequeue
- `Runner Bootstrap Preflight` runs remain queued after dispatch

## Current example

Known incident anchors from 2026-04-13:

- patched `E2E Smoke Dev` validation run: `24345753283`
- failed `E2E Smoke Dev` before the auth fix: `24345028436`

At the time of this checklist, the observed pattern was:

- one heavy runner online and idle with the expected heavy labels
- one light runner online and idle but unlabeled
- multiple queued workflows not starting, including smoke and preflight jobs

That pattern points to stale ARC registration or scale-set reconciliation, not just raw
runner capacity.

## Operator sequence

### 1. Confirm the unhealthy state

Run:

```bash
gh api repos/philipplukas/evidara/actions/runners \
  --jq '.runners[] | {name,status,busy,labels:[.labels[].name]}'
```

Record:

- which runners are online
- whether the light runner has the full label set
- whether the heavy runner is idle but jobs are still queued

### 2. Check for a real queue backlog

Run:

```bash
gh run list --status queued --limit 20
```

If queued self-hosted jobs include `E2E Smoke Dev`, `Runner Bootstrap Preflight`,
`Document Intelligence`, or `Runtime Images` while matching runners look idle, assume
registration drift first.

### 3. Recycle ARC runner registration

Use the MacConfig / cluster-admin environment to recycle the runner registration or
runner pods for the affected scale sets.

Minimum cluster actions:

```bash
kubectl get pods -n actions-runner-system -o wide
kubectl get autoscalingrunnersets -n actions-runner-system
kubectl delete pod -n actions-runner-system -l app.kubernetes.io/part-of=gha-runner-scale-set
```

If the runner controller or listeners are stale, also inspect:

```bash
kubectl logs -n actions-runner-system deploy/actions-runner-controller --tail=200
kubectl describe autoscalingrunnerset evidara-light -n actions-runner-system
kubectl describe autoscalingrunnerset evidara-heavy -n actions-runner-system
```

### 4. Reconfirm live labels after recycle

Run again:

```bash
gh api repos/philipplukas/evidara/actions/runners \
  --jq '.runners[] | {name,status,busy,labels:[.labels[].name]}'
```

Pass:

- light runner has `self-hosted`, `linux`, `x64`, `evidara`, `light`, `k8s`
- heavy runner has `self-hosted`, `linux`, `x64`, `evidara`, `heavy`, `k8s`

Fail:

- any runner returns with `labels: []`
- expected labels are incomplete

### 5. Rerun pool verification before product workflows

Run:

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

Pass:

- both preflight runs start promptly
- light proves Node/Python bootstrap
- heavy proves Playwright/browser bootstrap
- runner-pool smoke completes without queue stalls

### 6. Only then rerun product workflows

After the pool checks pass:

1. rerun `E2E Smoke Dev`
2. if green, rerun strict `Release Readiness`
3. rerun any previously stuck `Runner Bootstrap Preflight` or other queued workflow only
   after the pool is stable

## Quick incident note for Linear

Suggested one-paragraph operator summary:

```text
Runner recycle required: self-hosted jobs remained queued even though a matching heavy runner appeared idle, and the light runner returned without labels. This points to ARC registration / scale-set reconciliation drift rather than raw capacity. Recycle the affected runner registration or pods, reconfirm full label sets, rerun light/heavy preflight plus runner-pool smoke, and only then rerun E2E Smoke Dev followed by strict Release Readiness.
```

## Done means

`TAR-238` can treat this incident as stabilized when:

- light and heavy pools both come back with the full label contract
- the preflight runs start without queue stalls
- `runner-pool-smoke.yml` passes after recycle
- `E2E Smoke Dev` actually starts and runs on the intended pool
