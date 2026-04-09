"""MCP server entrypoint for repo-local Zed workflows."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from evidara_zed_mcp.catalog import (
    change_sync_requirements as get_change_sync_requirements,
    component_quality_gate as get_component_quality_gate,
    narrowest_check_for_path as get_narrowest_check_for_path,
    repo_overview as get_repo_overview,
    resolve_repo_root,
    search_contracts as get_contract_matches,
    search_docs as get_doc_matches,
    search_runbooks as get_runbook_matches,
)

mcp = FastMCP("evidara")


def _repo_root():
    return resolve_repo_root(os.environ.get("EVIDARA_REPO_ROOT"))


@mcp.tool()
def repo_overview() -> dict[str, Any]:
    """Return the top-level Evidara component map and canonical source-of-truth paths."""

    return get_repo_overview()


@mcp.tool()
def component_quality_gate(component: str) -> dict[str, str]:
    """Return the preferred quality-gate command and docs path for a component."""

    return get_component_quality_gate(component)


@mcp.tool()
def change_sync_requirements(change_type: str) -> dict[str, Any]:
    """Return AGENTS-driven sync surfaces for a given Evidara change classification."""

    return get_change_sync_requirements(change_type)


@mcp.tool()
def narrowest_check_for_path(path: str) -> dict[str, str]:
    """Return the smallest repo-specific quality gate recommendation for a changed path."""

    return get_narrowest_check_for_path(path)


@mcp.tool()
def search_contracts(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search the contracts tree for a plain-text query."""

    return get_contract_matches(_repo_root(), query=query, limit=limit)


@mcp.tool()
def search_docs(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search the docs tree for a plain-text query."""

    return get_doc_matches(_repo_root(), query=query, limit=limit)


@mcp.tool()
def search_runbooks(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search runbooks under docs/runbooks for a plain-text query."""

    return get_runbook_matches(_repo_root(), query=query, limit=limit)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
