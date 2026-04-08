# Documentation Governance

## Purpose

This directory contains the rules, policies, and templates that govern how Evidara documentation is written, maintained, and kept in sync with the codebase.

## Contents

| Document | Purpose |
|----------|---------|
| [Anti-Drift Strategy](anti-drift-strategy.md) | How we prevent and detect documentation drift |
| [Update Rules](update-rules.md) | When and how documentation must be updated |
| [Doc Types and Authority](doc-types-and-authority.md) | What types of docs exist and which is authoritative |
| [Review Checklist](review-checklist.md) | Checklist for reviewing documentation changes |
| [Stale Doc Policy](stale-doc-policy.md) | How we handle stale documentation |
| [AI PR Review Prompt](ai-pr-review-prompt.md) | Prompt for AI-assisted PR review |

## Templates

| Template | Use for |
|----------|---------|
| [Component Doc Template](templates/component-doc-template.md) | New component documentation |
| [Runbook Template](templates/runbook-template.md) | New operational runbooks |
| [Setup Doc Template](templates/setup-doc-template.md) | New developer setup guides |
| [Testing Doc Template](templates/testing-doc-template.md) | New component testing guides |
| [ADR Template](templates/adr-template.md) | New architecture decision records |

## Local MkDocs output (`site/`)

`python3 -m mkdocs build` and [`scripts/check_docs.sh`](../../scripts/check_docs.sh) write the static HTML site to **`site/`** at the repository root (MkDocs default). That directory is **gitignored**; do not add or commit it. Published docs are built from `docs/` + `mkdocs.yml` in CI / GitHub Pages, not from a checked-in `site/`.

If you already have an untracked `site/` from an older clone, delete it once (`rm -rf site/`) or simply leave it—after updating `.gitignore`, Git ignores it. Prefer `mkdocs serve` for local preview when you only need a browser and not a full strict build artifact.

## Key Principle

**Deterministic checks fail builds. AI checks suggest.**

Pre-commit hooks and CI enforce structure, schemas, and link validity. AI review suggests missing doc updates. Humans make the final call.
