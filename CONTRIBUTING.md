# Contributing to Evidara

## Clean-Room Implementation

This is a **clean-room implementation**. All contributions must adhere to the [clean-room principles](docs/architecture/clean-room-principles.md). Do not copy source code, tests, prompts, or proprietary documentation from prior repositories.

## Branch Naming

Use short-lived branches from `main` with these prefixes:

| Prefix | Purpose |
|--------|---------|
| `feat/` | New features or capabilities |
| `fix/` | Bug fixes |
| `chore/` | Maintenance, refactoring, dependency updates |
| `docs/` | Documentation changes |
| `adr/` | Architecture decision records |

**Examples:**

```
feat/platform-control-source-registry
fix/legal-search-pagination
docs/repository-bootstrap
adr/0007-auth-strategy
```

## Pull Request Expectations

1. **One concern per PR.** Keep PRs focused on a single logical change.
2. **Describe what and why.** The PR description should explain the change and its rationale.
3. **Update documentation.** If your change affects architecture, boundaries, or contracts, update the relevant docs.
4. **Add an ADR for architecture changes.** Any significant architecture decision must be captured in an ADR in `docs/adr/`.
5. **No direct production changes without review.** All changes to `main` must go through a pull request with at least one approval.

## Contract Changes

Changes to files in `contracts/` require additional scrutiny:

- Clearly describe what changed and why in the PR description.
- Tag affected component owners for review.
- Verify backwards compatibility or document breaking changes.
- Update any related ADRs or architecture docs.

## Code Review

- At least **1 approval** is required before merging.
- Stale approvals are dismissed when new commits are pushed.
- Force pushes to `main` are not allowed.

## Commit Messages

Use clear, descriptive commit messages. Prefer conventional-style prefixes:

```
feat: add source registry schema
fix: correct OpenSearch index mapping
docs: update storage model architecture doc
chore: update Terraform provider versions
```

## Questions?

If you are unsure about boundaries, ownership, or conventions, check:

- [docs/architecture/repository-structure.md](docs/architecture/repository-structure.md)
- [docs/architecture/boundary-contracts.md](docs/architecture/boundary-contracts.md)
- [docs/architecture/implementation-principles.md](docs/architecture/implementation-principles.md)
