# Branch Rules

## Status

Convention-based (not enforced by GitHub branch protection — requires GitHub Pro for private repos).

## Rules for `main`

1. **No direct pushes to main.** All changes go through pull requests.
2. **Squash-merge only.** Every merge to main produces one clean commit.
3. **Semantic PR title required.** The PR title must use a conventional commit prefix. CI validates this automatically.
4. **CI must pass.** Do not merge with failing checks.
5. **Review before merge.** At least one review (human or AI) before merging.
6. **Stale reviews dismissed.** When new commits are pushed, previous approvals are considered stale.

## Allowed PR title prefixes

| Prefix | Purpose |
|---|---|
| `feat:` | New features or capabilities |
| `fix:` | Bug fixes |
| `chore:` | Maintenance, refactoring, dependency updates |
| `docs:` | Documentation changes |
| `ci:` | CI/CD workflow changes |
| `refactor:` | Code restructuring without behavior change |
| `test:` | Test-only changes |
| `style:` | Formatting, whitespace (no logic change) |
| `perf:` | Performance improvements |

## Component scope (optional)

Add a scope in parentheses to indicate the affected component:

```text
feat(legal-search): add jurisdiction filter
fix(platform-control): correct run state transition
docs(adr): ADR-0008 caching strategy
chore(infra): update GCP provider version
```

## Branch naming

Use short-lived branches from `main` with these prefixes:

- `feat/` — new features
- `fix/` — bug fixes
- `chore/` — maintenance
- `docs/` — documentation
- `adr/` — architecture decisions

## Why convention-based

The repo is private and on GitHub Free, which does not support branch protection rules. These conventions are enforced by:

- **CI** — the `pr-title` workflow blocks merge if the title format is wrong
- **Team discipline** — every team member follows these rules
- **CodeRabbit** — AI review catches rule violations

When the repo moves to GitHub Pro or becomes public, these conventions can be enforced via branch protection rules.
