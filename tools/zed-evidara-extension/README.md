# Evidara Zed Extension

Thin Zed MCP extension wrapper for the repo-local
[`zed-evidara-mcp`](../zed-evidara-mcp/) Python server.

## Purpose

This package exists so the existing Evidara MCP server can be installed in Zed
as a dev extension. The Rust layer does not implement MCP behavior itself. It
only reads Zed context-server settings and launches:

```bash
uv run --directory <repo_root>/tools/zed-evidara-mcp evidara-zed-mcp
```

## Prerequisites

- `uv` on `PATH`
- Rust via `rustup`, because Zed builds dev extensions locally

## Install in Zed

1. Open Zed.
2. Run `Extensions: Install Dev Extension`.
3. Select `tools/zed-evidara-extension`.
4. Set the `repo_root` context-server setting to the Evidara repo root.

The checked-in [Zed setup doc](../../docs/setup/zed.md) includes the matching
settings snippet.
