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

```text
feat/platform-control-source-registry
fix/legal-search-pagination
docs/repository-bootstrap
adr/0007-auth-strategy
```

## Merge Strategy

- **Squash-merge only.** Every merge to main produces one clean commit.
- **Semantic PR title required.** PR titles must use one of the following prefixes (enforced by CI):

  | Prefix | Purpose |
  |---|---|
  | `feat` | New features or capabilities |
  | `fix` | Bug fixes |
  | `chore` | Maintenance, dependencies, config |
  | `docs` | Documentation changes |
  | `ci` | CI/CD workflow changes |
  | `refactor` | Code restructuring without behavior change |
  | `test` | Test-only changes |
  | `style` | Formatting, whitespace (no logic change) |
  | `perf` | Performance improvements |

  Optional scope in parentheses: `feat(legal-search): add jurisdiction filter`

- **The PR title becomes the commit message on main.**

See [docs/setup/branch-rules.md](docs/setup/branch-rules.md) for the full branch rule set.

## Pull Request Expectations

1. **One concern per PR.** Keep PRs focused on a single logical change.
2. **Classify the change.** Use the PR template to check the change type (user-visible, contract, infra, etc.).
3. **Describe what and why.** The PR description should explain the change and its rationale.
4. **Update documentation.** If your change affects architecture, boundaries, or contracts, update the relevant docs.
5. **Add an ADR for architecture changes.** Any significant architecture decision must be captured in an ADR in `docs/adr/`.
6. **Explain omissions.** If docs, tests, or specs were intentionally left unchanged, say why.

## Sync Checks

When making a change, inspect likely sync neighbors:

| Change type | Check these |
|---|---|
| User-visible behavior | Tests, feature docs, runbook if operator flow changed |
| Contract change | OpenAPI/JSON Schema, generated clients, contract tests |
| Infra change | Terraform docs, infra runbook, deployment guides |
| Pipeline change | Data quality checks, pipeline docs, failure-mode notes |
| Architecture change | `structurizr/workspace.dsl`, ADR, `docs/architecture/` |

If no sync update was needed, say so in the PR description.

## Source of Truth

| Thing | Canonical source |
|---|---|
| Architecture | `structurizr/workspace.dsl` |
| API interfaces | `contracts/api/*.openapi.yaml` |
| Entity shapes | `contracts/schemas/*.json` |
| Event payloads | `contracts/events/*.json` |
| Infra resources | `infra/terraform/` |
| Tests | Test files adjacent to code |
| Narrative docs | `docs/` |

**Rules:**

- Prefer generated docs over duplicated prose
- Structurizr is canonical architecture; Mermaid is for docs-local explanation only
- OpenAPI and JSON Schema are interface truth
- Terraform docs should be generated via terraform-docs

## Contract Changes

Changes to files in `contracts/` require additional scrutiny:

- Clearly describe what changed and why in the PR description.
- Tag affected component owners for review.
- Verify backwards compatibility or document breaking changes.
- Update any related ADRs or architecture docs.

## Required Local Checks

Run before opening a PR:

```bash
pre-commit run --all-files
```

This runs markdownlint, schema validation, contract checks, doc checks, and legal-search typecheck/lint/test.

Documentation checks now include Mermaid validation. Install the pinned repo-root Node dependencies once with `npm install` so `npm run --silent check:mermaid` is available locally.

## Code Review

- At least **1 review** (human or AI) is required before merging.
- Stale approvals are dismissed when new commits are pushed.
- Force pushes to `main` are not allowed.

## Commit Messages

Use clear, descriptive commit messages. Prefer conventional-style prefixes:

```text
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
