# TAR-77 branch protection evidence (2026-04-21)

## Source

GitHub API `GET /repos/{owner}/{repo}/branches/main/protection` verified 2026-04-21.

## Branch protection settings for `main`

| Setting | Value |
|---------|-------|
| `required_status_checks.strict` | **true** — branch must be up to date before merging |
| `required_status_checks.checks` | `check-title`, `contract-validation` |
| `enforce_admins` | **false** |
| `required_pull_request_reviews` | **null** (not configured) |
| `required_linear_history` | **false** |

## Required checks detail

Both required checks are always-on workflows that fire on every PR:

- **check-title** — validates PR title format
- **contract-validation** — validates contract schema compliance

This matches the TAR-70 gate policy hardening model (2026-04-20) which restricts
required checks to always-on contexts only. Path-filtered workflows (Release
Readiness, scraping-qa, etc.) remain release-evidence gates but are not branch
protection required checks.

## Known gaps

- **`enforce_admins` is false.** Admins can bypass the required checks. This was
  already accepted as part of TAR-70 evidence (see
  [ga-operator-board.md](../ga-operator-board.md) — TAR-70 lane). The rationale
  is that admin bypass is needed for emergency fixes; the risk is mitigated by
  limiting the admin set and requiring post-merge audit for any bypass.
- **No required pull request reviews.** PRs can be merged without review approval.
  This is a known tradeoff for the current team size and velocity; it does not
  block GA.

## Policy lineage

This evidence links back to TAR-70 gate policy hardening (2026-04-20). The GA
operator board records:

> Branch protection set 2026-04-20: strict=true, required checks=[check-title,
> contract-validation].

TAR-77 confirms that the protection settings remain in effect as of 2026-04-21.
