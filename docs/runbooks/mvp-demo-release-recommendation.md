# MVP Demo Package and Release Recommendation

Owner: Platform team
Last reviewed: 2026-04-06
Last verified: 2026-04-06
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
- `docs/runbooks/runtime-stack.md` (release-lane operation)

## Current Recommendation

Decision: **Conditional GO (technical + website surface availability)**.

Rationale:

- Technical readiness signal is green (`Release Readiness` strict `GO`).
- API-level MVP flow evidence is present in dev and staging.
- Website surfaces are published and reachable in dev/staging:
  - legal-search frontend (dev/staging)
  - platform-control admin UI (dev/staging)
- Remaining risk is demo-quality polish (metadata credibility and screenshot pack),
  not runtime accessibility.

## Remaining Risks

- `TAR-89`: improve search/detail metadata quality for user trust
- Operator screenshot evidence pack for canonical demo walkthrough

## Active Quality Stream

- `TAR-89`: improve search/detail metadata quality for user trust

## Final Release Gate For Product Sign-off

Promote to full product `GO` only when all are true:

1. `TAR-87` and `TAR-88` completed with walkthrough evidence attached
2. Acceptance scenario pack rerun and passing in dev and staging
3. No unresolved blocker findings in website walkthrough
4. Latest `Release Readiness` run remains `GO`
