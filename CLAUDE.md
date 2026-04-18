@AGENTS.md

## Claude Code quick reference

Repo-wide conventions live in `AGENTS.md` (imported above). This file only adds Claude-Code-specific pointers not covered there.

### Planning anchor

Active roadmap: see issue **#279** (proposed milestones M1–M6 for the 12 currently-open issues). Prefer `/issue-execute <number>` when working a ticket off that roadmap.

### Per-surface quality gates

Run the narrowest gate for the surface you touched before pushing:

| Surface | Gate |
|---|---|
| `platform-control/` | `cd platform-control && uv run pytest` |
| `platform-control/admin/` | `cd platform-control/admin && npm run check` |
| `legal-search/api/` | `cd legal-search/api && npm test` |
| `legal-search/frontend/` | `cd legal-search/frontend && npm run check` |
| `country-overlays/` or `platform-control/seeds/` | `python scripts/check_country_overlay_files.py` |
| Any scraping-touching PR | `bash scripts/check-scraping-qa.sh` |

### ID contract (see #264)

Canonical seeds: `platform-control/seeds/reference/{authorities,jurisdictions,compliance_policies,extractor_profiles}.yaml`.
Legacy (being retired): `platform-control/src/platform_control/hierarchies/{authorities,jurisdictions}.yaml`.
Any PR that renames or adds an `authority_id` / `jurisdiction_id` must keep the canary script `scripts/ch-fedlex-fast-loop.sh` functional — it hardcodes `auth_fedlex` and `jur_ch_federal`.

### Alembic

Migrations under `platform-control/`. Current head at time of M0: `20260417_0010` (see #253 for staging/prod rollout).

### ADRs

`docs/adr/` — numbered. Add one for any architecture-level decision (see AGENTS.md rule on `architecture-change`).
