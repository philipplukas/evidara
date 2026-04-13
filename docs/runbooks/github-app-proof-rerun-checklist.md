# GitHub app proof rerun checklist

Owner: Platform / release  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: staging proof after a `github-app` GitOps image-pin change lands in the real source-of-truth repo

## Purpose

Use this checklist after the `github-app` image pin is updated in the actual GitOps repo and
Argo has had a chance to resync. The goal is to prove the full chain end to end:

`GitHub -> app ingress -> Temporal -> runtime -> run record`

This checklist is intentionally evidence-first. It gives the operator one place to record the
exact URLs and IDs needed for sign-off.

## Important scope note

The current Evidara repo does **not** contain the live `github-app` workload pin in
`k8s/gitops/staging/`; this repo still carries a placeholder GitOps root. The most likely
source-of-truth path for the actual workload pin is in the separate `rocky-agents` repo under
`k8s/overlays/staging/`, while Argo `Application` wiring may live in MacConfig.

Use this checklist only after the real pin change has landed in the actual source repo.

## Evidence header

Fill these in first:

- GitOps PR URL: `...`
- GitOps merge commit / revision: `...`
- Argo application name: `...`
- Argo sync timestamp (UTC): `...`
- GitHub run / event URL: `...`
- Temporal execution ID: `...`
- Platform-control run ID: `...`

## 2026-04-13 live execution note

This checklist was exercised live on 2026-04-13 against the Hetzner / Tailscale-backed
`evidare-staging` cluster after resolving cluster access and Argo branch drift.

Recorded evidence:

- GitOps PR URL: not needed for this execution; the pin was already present on `rocky-agents` `main`
- GitOps merge commit / revision: `c7f70ad135cda6e17835a2345bd9d6e603f090ca`
- Argo application name: `rocky-agents-staging`
- Argo sync timestamp (UTC): `2026-04-13T14:26:36Z` for the last successful pre-fix sync on the drifted branch; app was then corrected back to `main` live
- GitHub run / event URL: engineer webhook smoke against `https://github-app-staging.88.99.26.120.sslip.io/webhooks/github`
- Temporal execution ID: not captured from the current service logs; the strongest workflow anchor captured was `workflow_id=github-pr-philipplukas-rocky-agents-7`
- Platform-control run ID: not applicable for this `rocky-agents` smoke; the durable audit anchor produced here was `run_id=fd4e311e-80bc-425c-8bcd-18a4f50f0e54`

Observed execution anchors:

- Live `github-app` image after correction: `ghcr.io/philipplukas/rocky-agents-github-app:sha-c7f70ad135cd`
- Runtime dispatch ID: `runtime-d56fdc406a2e4d4fbcee247fba03b319`
- Namespace: `evidare-staging`
- Argo health / sync status after correction: `Healthy`, `Synced`

Important finding:

- The cluster was not wrong because of a missing image pin. The real drift was that Argo
  `rocky-agents-staging` had been switched to `targetRevision: codex/temporal-next` instead of
  `main`, which left the live deployment on `sha-5f517f1f96c4`. Correcting the application back
  to `main` allowed the deployment to roll back onto `sha-c7f70ad135cd`.

Current proof strength:

- Proven:
  - staging cluster reachable over Tailscale
  - `rocky-agents-staging` Argo application is healthy and synced
  - live `github-app` deployment is on `sha-c7f70ad135cd`
  - engineer webhook smoke accepted with HTTP `202`
  - workflow start/signal path accepted by `agent-orchestrator`
  - downstream runtime dispatch accepted with HTTP `200`
  - durable run record emitted in the smoke response payload
- Still not captured in evidence:
  - explicit Temporal execution ID from service logs
  - a platform-control run ID, because this smoke stayed inside the `rocky-agents` stack

## 1. Confirm the GitOps pin landed

Record:

- GitOps PR URL: `...`
- merged revision / commit: `...`
- target image pin: `sha-c7f70ad135cd`

Pass:

- the actual product GitOps repo shows the `github-app` staging workload updated to the target sha
- the merge commit is on the branch Argo watches for staging

## 2. Confirm Argo synced the new revision

Record:

- Argo application name: `...`
- sync status screenshot/export: `...`
- health status screenshot/export: `...`

Pass:

- app is `Synced`
- app is `Healthy`
- workload revision reflects the merged GitOps commit

If manual sync is required, record the command or UI action used.

## 3. Confirm the staging workload is on the expected image

Record:

- workload name: `...`
- deployed image reference: `...`
- observed image digest / sha: `...`

Pass:

- the live staging workload resolves to `sha-c7f70ad135cd`
- any rollout/restart finished successfully

## 4. Trigger the GitHub side of the proof

Choose the exact GitHub event or workflow that should exercise the `github-app` path.

Record:

- GitHub workflow/event name: `...`
- GitHub run URL: `...`
- trigger timestamp (UTC): `...`

Pass:

- GitHub accepted the trigger
- the event reached the intended staging path

## 5. Confirm app ingress / handoff succeeded

Capture the earliest runtime evidence that the GitHub-side event hit the application.

Record:

- ingress log / request ID / event ID: `...`
- staging service URL or route: `...`
- any webhook delivery ID or request correlation ID: `...`

Pass:

- the staging `github-app` path received the request
- the request was not rejected at auth/routing level

## 6. Confirm Temporal progression

Use the rollout guidance in
[platform-control-wizard-temporal-argilla-rollout.md](../setup/platform-control-wizard-temporal-argilla-rollout.md)
if the flow uses Temporal-backed orchestration.

Record:

- Temporal namespace: `...`
- workflow / execution ID: `...`
- task queue / worker identity if relevant: `...`

Pass:

- the expected Temporal execution exists
- it progressed past initial start
- it did not stall because of missing worker or config

## 7. Confirm runtime-side processing

Record:

- platform-control API health URL/result: `...`
- relevant runtime log excerpt or event trace: `...`
- any downstream component handoff result: `...`

Pass:

- the runtime path processed the request rather than only accepting it
- no blocking runtime error occurred between ingress and persistence

## 8. Confirm the platform-control run record

This is the audit anchor for the end-to-end proof.

Record:

- platform-control run ID: `...`
- run status / phase progression: `...`
- any linked source/version identifiers: `...`

Pass:

- the expected run record exists
- the record reflects the triggered proof flow
- the run status is consistent with the Temporal/runtime evidence

## 9. Final evidence bundle

Attach or link all of the following in one place:

- GitOps PR URL
- GitOps merge revision
- Argo app sync proof
- deployed image sha proof
- GitHub run URL
- ingress/request correlation proof
- Temporal execution ID
- platform-control run ID

## Ready-to-paste proof summary

```text
GitHub app staging proof rerun — <date>

GitOps:
- PR: <gitops_pr_url>
- merged revision: <gitops_merge_revision>
- pinned image: sha-c7f70ad135cd

Argo:
- app: <argo_app_name>
- sync status: <synced/healthy evidence>

Execution proof:
- GitHub run/event: <github_run_url>
- Temporal execution: <temporal_execution_id>
- platform-control run: <platform_control_run_id>

Outcome:
- GitHub event reached staging github-app
- Temporal workflow/execution started and progressed
- runtime path completed far enough to create/update the expected run record
```

## Done means

This proof is complete when all of these are true:

- the pin is merged in the real GitOps repo
- Argo synced the new revision
- the live staging workload is on `sha-c7f70ad135cd`
- the GitHub trigger reached the app
- the Temporal execution exists and progressed
- the platform-control run record exists and matches the flow
