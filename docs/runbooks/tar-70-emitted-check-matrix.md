# TAR-70 emitted-check matrix

Owner: Platform / release  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: PR-required checks, branch-protection policy, merge-gate validation

## Purpose

This note is the operator-facing matrix for deciding which GitHub checks can safely be
treated as universal required checks and which must stay path-scoped or release-scoped.
Use it before changing branch protection for `main`.

It is intentionally small:

- it summarizes the checks our current workflows emit by PR type
- it highlights the minimum universal gate we should keep in branch protection
- it leaves live branch-protection changes out of scope

## Recommended policy model

Keep the universal required-check list limited to checks that emit on every PR:

- `PR Title / check-title`
- `Docs and Contracts Checks / contract-validation`

Keep component and release checks path-scoped or release-scoped unless an
always-on aggregator workflow exists.

Do not require these universally yet:

- `Legal Search / api`
- `Legal Search / frontend`
- `Platform Control / check`
- `Document Intelligence / document-intelligence-check`
- `Document Intelligence / document-intelligence-runtime-check`
- `Terraform / *`
- `Runtime Images / *`
- `Release Readiness / release-readiness`
- `scraping-qa`

## PR type vs emitted checks

| PR type | Emitted checks you should expect | Policy note |
|---|---|---|
| Docs-only PR | `PR Title / check-title`, `Docs and Contracts Checks / contract-validation` | Safe universal baseline; docs workflows should not depend on component gates. |
| Legal-search frontend PR | `PR Title / check-title`, `Docs and Contracts Checks / contract-validation`, `Legal Search / frontend`, relevant `Runtime Images` jobs | Keep frontend image builds path-scoped; do not require them on docs-only PRs. |
| Legal-search API PR | `PR Title / check-title`, `Docs and Contracts Checks / contract-validation`, `Legal Search / api`, relevant `Runtime Images` jobs | API image build is path-scoped and should not block unrelated PRs. |
| Platform-control PR | `PR Title / check-title`, `Docs and Contracts Checks / contract-validation`, `Platform Control / check`, relevant `Runtime Images` jobs | Treat admin/worker/platform images as component gates, not universal gates. |
| Document-intelligence PR | `PR Title / check-title`, `Docs and Contracts Checks / contract-validation`, `Document Intelligence / document-intelligence-check` | Runtime/deployment checks should stay limited to the paths that trigger them. |
| Document-intelligence runtime / deployment PR | Above, plus `Document Intelligence / document-intelligence-runtime-check` and `Runtime Images / Build document-intelligence consumer image` | Keep the runtime check tied to deployment-relevant paths. |
| Terraform / infra PR | `PR Title / check-title`, `Docs and Contracts Checks / contract-validation`, `Terraform / fmt-check`, `Terraform / plan-dev`, `Terraform / plan-staging` (and Databricks equivalents when relevant) | Terraform jobs are important, but they are not universal PR gates. |
| Release / evidence run | `Release Readiness / release-readiness`, `scraping-qa` when the workflow or paths trigger them | These are release-lane gates; keep them out of universal branch protection unless they always emit. |

## Validation rule

Before adding a required status check to `main`, ask:

1. Does this check emit on every PR type in the matrix above?
2. If not, can it be wrapped in an always-on aggregator that always emits one stable context?
3. If not, keep it path-scoped or release-scoped instead of universal.

## Operator use

Use this matrix when:

- updating GitHub branch protection
- reviewing why a PR is blocked by required checks
- deciding whether a workflow belongs in `main` protection
- writing Linear comments for `TAR-70`, `TAR-214`, or `TAR-160`

## Related docs

- [Gate policy hardening](tar-70-gate-policy-hardening.md)
- [Branch rules](../setup/branch-rules.md)
- [GA operator board](ga-operator-board.md)
