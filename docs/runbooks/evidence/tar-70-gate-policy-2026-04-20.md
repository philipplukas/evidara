# TAR-70 Gate Policy Evidence (2026-04-20)

## Branch protection configuration

Applied via `gh api repos/philipplukas/evidara/branches/main/protection`:

- **strict**: true (branch must be up to date before merging)
- **required checks**: `check-title`, `contract-validation`
- **enforce_admins**: false
- **required_pull_request_reviews**: none
- **restrictions**: none

## Rationale

Per `docs/runbooks/tar-70-gate-policy-hardening.md` §2:

1. **Universal PR gate**: Only `check-title` (PR Title workflow) and `contract-validation`
   (Docs and Contracts Checks workflow) emit on every PR regardless of paths changed.
2. **Path-specific gates**: Platform Control, Legal Search, Document Intelligence, Runtime
   Images, Scraping QA, Terraform — all path-filtered, gate only relevant PRs.
3. **Release-lane gates**: Release Readiness and scraping-qa remain evidence gates for
   go/no-go decisions, not universal PR blockers.

## Workflow audit

| Workflow | Trigger | Context | Always-on? |
|----------|---------|---------|------------|
| PR Title | all PRs | check-title | YES — required |
| Docs and Contracts | all PRs | contract-validation | YES — required |
| Platform Control | platform-control/** | check | no |
| Legal Search | legal-search/** | api, frontend | no |
| Document Intelligence | document-intelligence/** | document-intelligence-check | no |
| Runtime Images | various paths | Detect changed paths | no |
| Scraping QA | scripts/**, country-overlays/** | scraping-qa | no |
| Terraform | infra/** | terraform | no |
