# Zed Setup

Use the checked-in [`.zed/settings.json`](../../.zed/settings.json) when working
on Evidara in Zed.

## What this config does

- Auto-installs language extensions that match the monorepo surface area:
  `Dockerfile`, `Make`, `Nix`, `SQL`, `Terraform`, and `XML`
- Excludes heavy generated/runtime directories from project scanning so the file
  tree and search stay responsive in this monorepo
- Registers a repo-local `evidara` MCP server backed by
  [`tools/zed-evidara-mcp/`](../../tools/zed-evidara-mcp/)

## First-time setup

1. Open the repository in Zed.
2. Trust the worktree when Zed prompts for project-level settings.
3. Ensure `uv` is installed and available on `PATH`.
4. Open the Agent Panel and confirm the `evidara` MCP server is available.

The MCP server is launched with:

```bash
uv run --directory tools/zed-evidara-mcp evidara-zed-mcp
```

## Included MCP tools

The repo-local MCP server currently exposes read-oriented tools for:

- repository overview and component ownership reminders
- quality-gate lookup per component
- narrowest quality-gate recommendation for a changed path
- AGENTS-aware sync requirements by change classification
- contract search under `contracts/`
- docs search under `docs/`
- runbook search under `docs/runbooks/`

This keeps the first version production-safe. Add execution-oriented tools only
after the team is comfortable with the trust and approval model inside Zed.

## Recommended Zed add-ons

The checked-in settings handle the core language support. Beyond that, the most
useful optional installs for Evidara are:

- `Context7 MCP Server` for current framework and library docs
- `Playwright MCP Server` for browser automation and page inspection
- `Linear MCP Server` if issue tracking happens in Linear

For agent workflows, prefer external agents that can use MCP inside Zed, such
as Codex or Claude Code.

## Packaging later as a Zed extension

The current setup runs the MCP server directly from the repo, which is the
smallest useful step. If the team wants one-click installation later, use the
checked-in dev-extension wrapper at
[`tools/zed-evidara-extension/`](../../tools/zed-evidara-extension/).

### Dev extension path

1. Install Rust with `rustup`, because Zed builds dev extensions locally.
2. Open Zed and run `Extensions: Install Dev Extension`.
3. Select `tools/zed-evidara-extension`.
4. Configure the extension-backed context server with the repo root:

```json
{
  "context_servers": {
    "evidara-mcp": {
      "settings": {
        "repo_root": "/absolute/path/to/evidara"
      }
    }
  }
}
```

The extension only shells out to the same Python MCP server that powers the
repo-local setup:

```bash
uv run --directory <repo_root>/tools/zed-evidara-mcp evidara-zed-mcp
```

Keep the repo-local `.zed/settings.json` path as the default for now. It has
fewer moving parts and does not require Rust on contributor machines.
