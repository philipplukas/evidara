# Platform-Control Retool Artifacts

Archived Retool control-panel artifacts kept in-repo as historical reference material.

## Purpose

Keep the internal control-panel shape in-repo so operators, reviewers, and future automation can
reason about the intended Retool setup without reverse-engineering an environment-specific app.
The primary operator path for preview review, production runs, and run diagnostics is now the
code-managed React-admin app in `platform-control/admin`.

## Contents

- `control-panel.manifest.yaml` — page, query, and action inventory for the control panel
- `SETUP.md` — step-by-step guide for assembling the Retool app from the checked-in artifacts
- `sql/` — direct-Postgres read queries used by Retool browse, detail, and diagnostics pages
- `workflows/run_firecrawl_preview.yaml` — workflow definition for preview orchestration
- `agents/source-setup-copilot.md` — bounded AI copilot prompt and tool contract

## Resource model

- `platform_control_db` is the direct Postgres resource for read views
- `platform_control_api` is the REST resource for business actions

This follows ADR-0006: Retool reads via Postgres and uses the API for actions with state logic.
These artifacts are no longer part of the primary local setup or operator-run workflow.
