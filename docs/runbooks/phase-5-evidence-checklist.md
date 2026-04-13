# Phase 5 — single-page evidence checklist (TAR-69)

Owner: Platform team
Last reviewed: 2026-04-13
Last verified: 2026-04-13
Applies to: **Linear TAR-69** (release readiness / promotion decision), **TAR-64**, **TAR-77**, **TAR-85**
**Posture note:** teams **without** a staging GCP project use **dev** for remote MVP acceptance (TAR-85); see [Environment strategy — dev-first](../setup/environment-strategy.md#operator-posture-dev-first-no-staging-gcp-project).

This page is the **one entry point** for operator evidence that unblocks [phase 5 go / no-go memo](phase-5-go-no-go-memo.md). Detailed steps stay in the linked runbooks; file artifacts on the **matching Linear issue** (not only in git).

For the current release-packet refresh, start with [TAR-214 release evidence refresh](tar-214-release-evidence-refresh.md). That note sequences the exact evidence refresh and synthesis steps so the TAR-69 summary comment can be updated last.

---

## When this checklist is “green”

All three rows below are done **and** the gate table in [phase-5-go-no-go-memo.md](phase-5-go-no-go-memo.md) is updated with evidence links.

| Linear | Gate | “Done” definition | Procedure |
|--------|------|-------------------|-----------|
| **TAR-64** | Dev vertical slice smoke ×2 | Two successful runs on **separate** occasions (different days or `main` commits); each includes **Gate D** `run_id` / `document_id` narrative | [M5 evidence checklist — TAR-64](m5-evidence-checklist.md#tar-64--dev-e2e-smoke-two-runs), [TAR-64 / TAR-85 evidence capture](tar64-tar85-evidence-capture.md), [first vertical slice exit gates — TAR-64 block](first-vertical-slice-exit-gates.md#tar-64-dev-smoke-evidence-attach-to-linear) |
| **TAR-77** | Branch protection | GitHub **main** requires **Release Readiness** (or your strict equivalent); **screenshot** of rule + **one green** strict workflow run URL | [M5 — TAR-77](m5-evidence-checklist.md#tar-77--required-check-on-main), [screenshot evidence discipline](screenshot-evidence-discipline.md) |
| **TAR-85** | Remote MVP acceptance | Fresh `evidara workflow mvp-acceptance` JSON/stdout against **dev** Cloud Run (or **staging** if you operate it) — note `evidence_pack_version` | [M5 — TAR-85](m5-evidence-checklist.md#tar-85--remote-mvp-acceptance-dev-or-staging), [MVP acceptance scenario pack](mvp-acceptance-scenario-pack.md) |

---

## Suggested order (dependencies)

1. **TAR-77** first if merges are unprotected (high risk in phase-5 memo risk register).
2. **TAR-64** in parallel with remote env prep (needs GCP / dev wiring per M5 §TAR-64).
3. **TAR-85** after **dev** (or staging) URLs and tokens are confirmed — same impersonation pattern as e2e.

---

## After evidence is attached

1. Paste or link artifacts in **TAR-69** (summary comment).
2. Update [phase-5-go-no-go-memo.md](phase-5-go-no-go-memo.md) §2 gate table (Result + Evidence link column).
3. If recommendation changes from **PENDING**, note date and owner in Linear **TAR-69** (canonical publish target per memo §1).

## Related

- [Linear M5 / Phase 5 handoff pack](linear-milestone5-handoff-pack.md) — issue templates and agent handoff text (paste into Linear)
- [MVP demo package and release recommendation](mvp-demo-release-recommendation.md) — evidence packet template
- [M5 evidence checklist](m5-evidence-checklist.md) — full operator steps including DI Pub/Sub debugging
- [E2E Smoke Dev workflow](../../.github/workflows/e2e-smoke-dev.yml) — optional CI path for TAR-64
