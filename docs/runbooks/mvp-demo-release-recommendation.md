# MVP Demo Package and Release Recommendation

Owner: Platform team
Last reviewed: 2026-04-08
Last verified: 2026-04-08
Applies to: dev, staging

## Objective

Provide an operator-facing demo package and an evidence-based release decision
for the current MVP product slice.

## Demo Package

Use this sequence for demos:

1. Show release-lane status (`Release Readiness` strict `GO` run).
2. Show platform-control runtime health and source listing endpoint.
3. Show legal-search query flow (`/v1/search`) and detail fetch (`/v1/documents/{id}`).
4. Call out current UX-quality findings and active remediation items.
5. Confirm dev -> staging parity using the acceptance scenario pack.

Primary artifacts:

- `docs/runbooks/mvp-website-walkthrough.md`
- `docs/runbooks/mvp-acceptance-scenario-pack.md`
- `docs/runbooks/interaction-flow-validation.md`
- `docs/runbooks/runtime-stack.md` (release-lane operation)

## Operator Evidence Packet

Attach one packet per release candidate or demo handoff:

| Packet item                  | Canonical source                                                       | What to attach                                                                                            |
| ---------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Release sign-off report      | `Release Readiness` strict workflow + `docs/runbooks/runtime-stack.md` | Latest strict `GO` report (strict GO required) plus run URL                                               |
| API acceptance evidence      | `docs/runbooks/mvp-acceptance-scenario-pack.md`                        | Latest dev + staging API/proxy evidence from `uv run evidara workflow mvp-acceptance` or the shell helper |
| Browser interaction evidence | `docs/runbooks/interaction-flow-validation.md`                         | Latest staging interaction-flow artifact, including screenshot pack and Playwright report                 |
| Narrative walkthrough note   | `docs/runbooks/mvp-website-walkthrough.md`                             | Short operator note covering what was shown, what still feels rough, and any open follow-up issues        |

## Release-Candidate Handoff

Use this order when preparing a demo or release recommendation:

1. Confirm the latest strict `Release Readiness` run is `GO` and capture the generated strict `GO` report.
2. Attach the latest API acceptance evidence for dev and staging from `[docs/runbooks/mvp-acceptance-scenario-pack.md](mvp-acceptance-scenario-pack.md)`.
3. Verify and attach the latest staging browser evidence via `scripts/check-latest-interaction-flow-evidence.sh --mode staging --branch main`.
4. Use `[docs/runbooks/mvp-website-walkthrough.md](mvp-website-walkthrough.md)` as the narrative overlay for the demo, not as a replacement for API or Playwright truth.
5. Paste the generated `Runbook Verification Log Row` from the `Release Readiness` report into `[docs/runbooks/first-vertical-slice-exit-gates.md](first-vertical-slice-exit-gates.md)` or the active release issue.

## Current Recommendation

Decision: **Conditional GO (technical + website surface availability)**.

Rationale:

- Technical readiness signal is green (`Release Readiness` strict `GO`).
- API-level MVP flow evidence is present in dev and staging.
- Browser interaction evidence is owned by the interaction-flow runbook and staging parity workflow.
- Website surfaces are published and reachable in dev/staging:
  - legal-search frontend (dev/staging)
  - platform-control admin UI (dev/staging)
- Remaining risk is demo-quality polish (metadata credibility), not runtime accessibility or evidence capture.

## Remaining Risks

- `TAR-89`: improve search/detail metadata quality for user trust

## Active Quality Stream

- See `TAR-89` in Remaining Risks.

## Final Release Gate For Product Sign-off

Promote to full product `GO` only when all are true:

1. `TAR-87` and `TAR-88` completed with walkthrough evidence attached
2. Latest operator evidence packet is attached to the active release issue or sign-off thread
3. Latest API acceptance evidence is green in dev and staging via `docs/runbooks/mvp-acceptance-scenario-pack.md`
4. Latest browser interaction evidence is green via `docs/runbooks/interaction-flow-validation.md`
5. No unresolved blocker findings in website walkthrough
6. Latest `Release Readiness` run remains `GO`
