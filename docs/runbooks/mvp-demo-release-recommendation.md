# MVP Demo Package and Release Recommendation

Owner: Platform team
Last reviewed: 2026-04-26
Last verified: 2026-04-26
Applies to: **dev** (primary remote surface for small teams), **staging** when operated, **prod** sign-off gates

## Objective

Provide an operator-facing demo package and an evidence-based release decision
for the current MVP product slice.

## Demo Package

Use this sequence for demos:

1. Show release-lane status (`Release Readiness` strict `GO` run).
2. Show platform-control runtime health and source listing endpoint.
3. Show legal-search query flow (`/v1/search`) and detail fetch (`/v1/documents/{id}`).
4. Call out current UX-quality findings and active remediation items.
5. Confirm remote acceptance using the scenario pack (**dev** when no staging GCP project; otherwise dev → staging parity).

Primary artifacts:

- `docs/runbooks/mvp-website-walkthrough.md`
- `docs/runbooks/mvp-acceptance-scenario-pack.md`
- `docs/runbooks/interaction-flow-validation.md`
- `docs/runbooks/runtime-stack.md` (release-lane operation)

## Operator Evidence Packet

Attach one packet per release candidate or demo handoff:

| Packet item | Canonical source | What to attach |
| --- | --- | --- |
| Release sign-off report | `Release Readiness` strict workflow + `docs/runbooks/runtime-stack.md` | Latest strict `GO` report (strict GO required), workflow run URL, and GitHub Actions artifact **release-readiness-&lt;run_id&gt;** (JSON gate snapshots uploaded with the run). |
| API acceptance evidence | `docs/runbooks/mvp-acceptance-scenario-pack.md` | Latest **dev** (and staging if operated) API/proxy evidence from `uv run evidara workflow mvp-acceptance` or the shell helper; JSON includes **evidence_pack_version** for auditability. |
| Hetzner HITL rescore evidence | `scripts/smoke-hetzner-hitl-rescore.sh` + `docs/runbooks/hitl-rollout.md` | Latest internal staging smoke JSON showing correction id, triggered workflow id, `rescore_outcome` of `changed` or `unchanged`, and metrics bucket increment. |
| E2E smoke drill JSON | `.github/workflows/e2e-smoke-dev.yml` (and `e2e-smoke-staging.yml` if you run staging) | Artifact **e2e-smoke-*-drill-&lt;run_id&gt;** (pairs `platform_control_run_id` with `legal_search_document_id` for Gate D narratives). |
| Browser interaction evidence | `docs/runbooks/interaction-flow-validation.md` | Latest **dev** or staging interaction-flow workflow run URL + GCS bundle prefix; manifest includes **TAR-67 / TAR-69** drill filing bullets when applicable. |
| Narrative walkthrough note | `docs/runbooks/mvp-website-walkthrough.md` | Short operator note covering what was shown, what still feels rough, and any open follow-up issues. |
| Phase 5 memo (optional) | `docs/runbooks/phase-5-go-no-go-memo.md` | Link or excerpt when the demo supports a go/no-go discussion (see memo section 2.1 for artifact names). |

## Release-Candidate Handoff

Use this order when preparing a demo or release recommendation:

1. Confirm the latest strict `Release Readiness` run is `GO`, capture the generated strict `GO` report, and download artifact **release-readiness-&lt;run_id&gt;** from that workflow run for the JSON snapshots.
2. Attach the latest API acceptance evidence for **dev** (and staging if operated) from `[docs/runbooks/mvp-acceptance-scenario-pack.md](mvp-acceptance-scenario-pack.md)` (note `evidence_pack_version` in the JSON).
3. For acquisition smoke, attach **e2e-smoke-dev-drill-&lt;run_id&gt;** from the latest green **E2E Smoke Dev** run (or staging equivalent if you operate staging).
4. Verify and attach the latest browser evidence via `scripts/check-latest-interaction-flow-evidence.sh --mode staging --branch main` or `--mode local` (script modes today); if you do not run staging workflows, attach equivalent evidence per [interaction-flow-validation](interaction-flow-validation.md).
5. Use `[docs/runbooks/mvp-website-walkthrough.md](mvp-website-walkthrough.md)` as the narrative overlay for the demo, not as a replacement for API or Playwright truth.
6. Paste the generated `Runbook Verification Log Row` from the `Release Readiness` report into `[docs/runbooks/first-vertical-slice-exit-gates.md](first-vertical-slice-exit-gates.md)` or the active release issue; follow [TAR-64 / TAR-85 evidence capture](tar64-tar85-evidence-capture.md) when attaching raw stdout.

## Current Recommendation

Decision: **Conditional GO (technical + Hetzner staging HITL verified)**.

Rationale:

- Technical readiness signal is green (`Release Readiness` strict `GO`).
- API-level MVP flow evidence is present in **dev** (and staging when operated).
- Hetzner staging has a seeded DI surface and a passing HITL rescore smoke
  (`rescore_outcome=unchanged`, metrics updated, no new failed bucket).
- Browser interaction evidence is owned by the interaction-flow runbook and parity workflows.
- Website surfaces are published and reachable in **dev** (and staging when operated):
  - legal-search frontend
  - platform-control admin UI
- Remaining risk is demo-quality polish (metadata credibility), not runtime accessibility or evidence capture.

## Remaining Risks

- `TAR-89`: improve search/detail metadata quality for user trust

## Active Quality Stream

- See `TAR-89` in Remaining Risks.

## Final Release Gate For Product Sign-off

Promote to full product `GO` only when all are true:

1. `TAR-87` and `TAR-88` completed with walkthrough evidence attached
2. Latest operator evidence packet is attached to the active release issue or sign-off thread
3. Latest API acceptance evidence is green in **dev** (and staging when operated) via `docs/runbooks/mvp-acceptance-scenario-pack.md`
4. Latest browser interaction evidence is green via `docs/runbooks/interaction-flow-validation.md`
5. No unresolved blocker findings in website walkthrough
6. Latest `Release Readiness` run remains `GO`
