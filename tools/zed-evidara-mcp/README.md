# Evidara Zed MCP

Repo-local Model Context Protocol server for Zed.

## Purpose

This server gives Zed agents a small set of Evidara-specific read tools without
needing to teach the agent the repo structure from scratch on every task.

Current tools:

- `repo_overview`
- `component_quality_gate`
- `narrowest_check_for_path`
- `change_sync_requirements`
- `search_contracts`
- `search_docs`
- `search_runbooks`

## Run locally

```bash
uv run --directory tools/zed-evidara-mcp evidara-zed-mcp
```

The checked-in [`.zed/settings.json`](../../.zed/settings.json) is already wired
to launch this server from the repository root.

## Test

```bash
cd tools/zed-evidara-mcp
uv run pytest
```

## Notes

- This first version is intentionally read-oriented and safe by default.
- A thin Zed dev-extension wrapper now lives in
  [`../zed-evidara-extension/`](../zed-evidara-extension/) and launches this
  package via `uv`.
