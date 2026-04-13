# TAR-77 - evidence prep for branch protection proof

Owner: Platform lead
Last reviewed: 2026-04-13
Last verified: 2026-04-13
Applies to: **TAR-77** (branch protection proof), **TAR-69** (phase 5 go/no-go summary)

Use this note to prepare the TAR-77 evidence packet quickly once a green strict `Release Readiness` run exists. This is a prep checklist only; it does **not** change branch protection or CI.

## Current facts

- `main` branch protection currently reports `strict: true` with no required status checks:
  - `contexts: []`
  - `checks: []`
- Current branch-protection API:
  - `gh api repos/philipplukas/evidara/branches/main/protection/required_status_checks`
- Latest known green strict `Release Readiness` run on `main`:
  - [24286820758](https://github.com/philipplukas/evidara/actions/runs/24286820758)
- Latest strict `Release Readiness` rerun on current `main`:
  - [24344823652](https://github.com/philipplukas/evidara/actions/runs/24344823652)
  - failed because the latest `E2E Smoke Dev` run was `cancelled`
- Latest `E2E Smoke Dev` rerun:
  - [24345028436](https://github.com/philipplukas/evidara/actions/runs/24345028436)
  - failed while minting Cloud Run ID tokens because runner egress to `iamcredentials.googleapis.com` was unavailable
- Auth-fix validation rerun:
  - [24345753283](https://github.com/philipplukas/evidara/actions/runs/24345753283)
  - queued at the time of this note

## Ready-to-post TAR-77 wording

Paste this into TAR-77 once the green strict run exists:

```text
TAR-77 evidence refresh — 2026-04-13

Branch protection on `main`:
- `strict: true`
- required status checks currently empty (`contexts: []`, `checks: []`)

Strict Release Readiness:
- latest green strict run on `main`: https://github.com/philipplukas/evidara/actions/runs/24286820758
- latest rerun on current `main`: https://github.com/philipplukas/evidara/actions/runs/24344823652
- current blocker: strict rerun failed because the latest E2E Smoke Dev run was cancelled, and the next smoke rerun failed on runner egress to `iamcredentials.googleapis.com`

Policy note:
- the earlier required-check model (`release-readiness` / `scraping-qa`) is no longer the live truth on `main`
- this evidence packet records the current branch-protection state and the green strict run URL for auditability

Linked follow-up:
- TAR-70: gate-policy hardening / required-check model recovery
```

## Ready-to-post TAR-69 wording

Paste this into TAR-69 when the packet is ready to close:

```text
TAR-69 update — 2026-04-13

The release-evidence packet is current enough to close once TAR-77 is re-verified with a green strict Release Readiness run.

Included evidence:
- TAR-77: branch-protection proof and strict Release Readiness run URL
- TAR-64: dev smoke evidence
- TAR-85: remote MVP acceptance evidence

Current blocker:
- strict Release Readiness cannot be refreshed yet because the latest E2E Smoke Dev rerun failed on runner egress to `iamcredentials.googleapis.com`

Policy note:
- branch-protection drift is tracked separately on TAR-70
- the release packet should link the current branch-protection facts, not older screenshots or stale required-check assumptions
```

## Current blockers

- No fresh green strict `Release Readiness` run on the current `main` yet.
- The last `E2E Smoke Dev` rerun failed due to runner egress to `iamcredentials.googleapis.com`.
- `main` no longer requires universal `release-readiness` / `scraping-qa`, so TAR-77 should be treated as current-state evidence, not as a historical assumption.

## Recommended attachment order

1. Capture the current `main` branch-protection screenshot or export.
2. Confirm a green strict `Release Readiness` run on the current `main`.
3. Attach both to TAR-77.
4. Post the TAR-69 summary comment linking TAR-77 plus the refreshed release packet.
5. If the branch-protection model still differs from the old docs, link the drift back to TAR-70.
