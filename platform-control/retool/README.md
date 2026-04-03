# Platform-Control Retool Artifacts

Versioned Retool control-panel artifacts for the `platform-control` operator flow.

## Purpose

Keep the internal control-panel shape in-repo so operators, reviewers, and future automation can
reason about the intended Retool setup without reverse-engineering an environment-specific app.

## Contents

- `control-panel.manifest.yaml` — page, query, and action inventory for the control panel
- `sql/` — direct-Postgres read queries used by Retool browse/filter pages
- `workflows/run_firecrawl_preview.yaml` — workflow definition for preview orchestration
- `agents/source-setup-copilot.md` — bounded AI copilot prompt and tool contract

## Resource model

- `platform_control_db` is the direct Postgres resource for read views
- `platform_control_api` is the REST resource for business actions

This follows ADR-0006: Retool reads via Postgres and uses the API for actions with state logic.
