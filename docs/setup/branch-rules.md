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
docs(adr): ADR-0011 NestJS caching note
chore(infra): update GCP provider version
```

## Branch naming

Use short-lived branches from `main` with these prefixes:

- `feat/` — new features
- `fix/` — bug fixes
- `chore/` — maintenance
- `docs/` — documentation
- `adr/` — architecture decisions

Avoid long-lived parked namespaces such as `pr/…` unless you are actively using them; stale lines should be **rebased onto current `main` and opened as a normal PR**, or deleted. See [Max parallel execution](../process/max-parallel-execution.md) (stale-branch policy).

## Git worktrees and `shelf/*` branches

Git allows only **one** checked-out worktree per branch name. If you use multiple clones (for example `evidara`, `evidara-next-pr`, `evidara-pr-stack`), only **one** worktree should use the branch name `main`.

**Convention in this repo:**

| Worktree role | Typical local branch | Tracks |
|---|---|---|
| Primary clone | `main` | `origin/main` |
| Extra worktrees | `shelf/<purpose>` | `origin/main` (or a feature branch) |

Examples: `shelf/next-pr`, `shelf/pr-stack`, `shelf/tar137-worktree`. Create with:

```bash
git fetch origin
git checkout -B shelf/my-worktree origin/main
```

To add a worktree directory (from repo root):

```bash
git worktree add -b shelf/other ../evidara-other origin/main
```

Remove a worktree when done:

```bash
git worktree remove ../evidara-other
git worktree prune
```

After removing the last checkout of a `shelf/*` branch, delete the local branch if you no longer need it: `git branch -d shelf/other`.

For **parallel streams** (which paths can merge independently), see [Parallel work streams](../process/parallel-work-streams.md).

## Required status checks

Keep the required-check model aligned to the TAR-70 emitted-check matrix:

- universal required checks should stay limited to checks that emit on every PR
- path-scoped component checks should only gate the PRs that trigger them
- release-lane checks such as `release-readiness` and `scraping-qa` should stay
  release-scoped unless they are wrapped by an always-on aggregator

For the current operator view of which PR types emit which checks, see
[TAR-70 emitted-check matrix](../runbooks/tar-70-emitted-check-matrix.md).

## Enforcement

These rules are enforced by:

- **Branch protection** — keep live required checks aligned with the TAR-70 matrix and
  avoid requiring release-only checks universally
- **CI** — the `pr-title` workflow blocks merge if the title format is wrong
- **Team discipline** — every team member follows these rules
- **CodeRabbit** — AI review catches rule violations
