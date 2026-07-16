@AGENTS.md

## Claude Code quick reference

Repo-wide conventions live in `AGENTS.md` (imported above). This file only adds Claude-Code-specific pointers not covered there.

### Planning anchor

The original M1–M6 roadmap (issue #279) ran its course by 2026-04-28 and is closed; every M1–M6 issue closed with it. **There is no current roadmap anchor.** Until a successor planning issue lands, source the next-action list from `gh pr list --state open` and `gh issue list --state open` directly. When opening new work, prefer `/issue-execute <number>` if a ticket exists; otherwise scope inline.

### Per-surface quality gates

Run the narrowest gate for the surface you touched before pushing:

| Surface | Gate |
|---|---|
| `platform-control/` | `cd platform-control && uv run pytest` |
| `platform-control/admin/` | `cd platform-control/admin && npm run check` |
| `legal-search/api/` | `cd legal-search/api && npm run check` |
| `legal-search/frontend/` | `cd legal-search/frontend && npm run check` |
| `country-overlays/` or `platform-control/src/platform_control/seeds/` | `python scripts/check_country_overlay_files.py` |
| Any scraping-touching PR | `bash scripts/check-scraping-qa.sh` |

### ID contract (see #264)

Canonical seeds: `platform-control/src/platform_control/seeds/reference/{authorities,jurisdictions,compliance_policies,extractor_profiles}.yaml`.
Legacy (being retired): `platform-control/src/platform_control/hierarchies/{authorities,jurisdictions}.yaml`.
Any PR that renames or adds an `authority_id` / `jurisdiction_id` must keep the canary script `scripts/ch-fedlex-fast-loop.sh` functional — it hardcodes `auth_fedlex` and `jur_ch_federal`.

### Alembic

Migrations under `platform-control/`. Current head at time of M0: `20260417_0010` (see #253 for staging/prod rollout).

### ADRs

`docs/adr/` — numbered. Add one for any architecture-level decision (see AGENTS.md rule on `architecture-change`).
