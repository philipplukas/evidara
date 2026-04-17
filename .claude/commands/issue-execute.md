---
description: Drive one open GitHub issue end-to-end (branch → plan → implement → PR) against the #279 roadmap
argument-hint: <issue-number>
---

Execute issue **#$1** from the `philipplukas/evidara` roadmap (tracked in #279).

Follow the six-step recipe below. Use the MCP GitHub tools for all GitHub interactions. Do not improvise — if a step's preconditions aren't met, stop and surface the gap to the user.

## 1. Scope

- Call `mcp__github__issue_read` (method `get`) for issue **#$1**. Read the body and acceptance criteria.
- Call `mcp__github__issue_read` (method `get_comments`) to catch any recent clarifications.
- Identify which milestone (M1–M6) this issue belongs to per #279. If unclear, ask the user.
- Identify the primary **surface** affected (`platform-control`, `platform-control/admin`, `legal-search/api`, `legal-search/frontend`, `country-overlays`, `docs`, `scripts`, or `infra`).

## 2. Branch

- Derive a slug from the issue title (kebab-case, ≤40 chars).
- Create branch `claude/issue-$1-<slug>` off `main` (unless the plan in #279 specifies a different base — e.g. #258 is sequenced after #264).
- Confirm working tree is clean before starting.

## 3. Explore

- Launch **one** Explore subagent (medium thoroughness) scoped to the surface identified in step 1.
- Prompt the subagent with: the issue body, the acceptance criteria, the surface path, and an instruction to identify existing utilities to reuse before designing anything new (per AGENTS.md rule 2).

## 4. Plan

- For issues labeled `type:ops` (e.g. #253), skip this step — the work is runbook-driven, not code.
- Otherwise: launch **one** Plan subagent with the Explore findings, the acceptance criteria, and the constraint to keep the change minimal and production-safe (AGENTS.md rule 1).

## 5. Implement + verify

- Make the changes per the plan.
- Run the **narrowest** gate for the surface (see `CLAUDE.md` → "Per-surface quality gates"):
  - `platform-control`: `cd platform-control && uv run pytest`
  - `platform-control/admin`: `cd platform-control/admin && npm run check`
  - `legal-search/api`: `cd legal-search/api && npm test`
  - `legal-search/frontend`: `cd legal-search/frontend && npm run check`
  - Overlays / seeds: `python scripts/check_country_overlay_files.py`
  - Scraping-adjacent: `bash scripts/check-scraping-qa.sh`
- Run `/review` on the diff before committing.
- Run `/security-review` **iff** the diff touches: alembic migrations, `**/*config*.{ts,py}`, `.env*`, auth/role logic, or `process.env` access.
- Commit with a focused message referencing the issue.

## 6. Ship

- Push the branch: `git push -u origin claude/issue-$1-<slug>`.
- Open a PR via `mcp__github__create_pull_request`:
  - Title: `<type>: <short description> (#$1)` where type ∈ {fix, feat, chore, docs, refactor}.
  - Body includes `Closes #$1`.
  - Base: `main`.
- Attach the issue's milestone via `mcp__github__issue_write` (method `update`, `milestone` param) — confirm the milestone exists first.
- Subscribe to PR activity: `mcp__github__subscribe_pr_activity`.
- Report the PR URL back to the user and wait for human review.

## Guardrails

- **Never** force-push, amend published commits, or bypass hooks (`--no-verify`).
- **Never** modify files outside the surface identified in step 1 without explicit user approval.
- **Never** assign the milestone until confirming it exists — the MCP tools silently accept invalid milestone numbers.
- If a gate fails, do **not** mask it. Report the failure and ask how to proceed.
