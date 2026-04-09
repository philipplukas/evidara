"""Shared repo helpers for the Evidara Zed MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SKIP_DIRS = {
    ".git",
    ".jj",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "site",
}


@dataclass(frozen=True)
class ComponentGuide:
    name: str
    path: str
    language: str
    quality_gate: str
    docs: str


_COMPONENTS = {
    "platform-control": ComponentGuide(
        name="platform-control",
        path="platform-control/",
        language="Python / FastAPI",
        quality_gate="cd platform-control && uv run pytest",
        docs="docs/components/platform-control.md",
    ),
    "document-intelligence": ComponentGuide(
        name="document-intelligence",
        path="document-intelligence/",
        language="Python / Databricks",
        quality_gate="bash scripts/check-document-intelligence.sh",
        docs="docs/components/document-intelligence.md",
    ),
    "legal-search": ComponentGuide(
        name="legal-search",
        path="legal-search/",
        language="TypeScript / Next.js / NestJS",
        quality_gate="cd legal-search && npm run check",
        docs="docs/components/legal-search.md",
    ),
    "contracts": ComponentGuide(
        name="contracts",
        path="contracts/",
        language="OpenAPI / JSON Schema",
        quality_gate="cd legal-search && npm run openapi:check",
        docs="docs/components/contracts.md",
    ),
    "infra": ComponentGuide(
        name="infra",
        path="infra/",
        language="Terraform / HCL",
        quality_gate="terraform fmt -check && terraform validate",
        docs="docs/components/infra.md",
    ),
}

_CHANGE_SYNC_REQUIREMENTS = {
    "internal-refactor": {
        "required_updates": ["focused tests when behavior risk exists"],
        "notes": ["Prefer small, production-safe edits and existing repo patterns."],
    },
    "user-visible-behavior": {
        "required_updates": [
            "focused tests",
            "feature docs in docs/components/ or legal-search/docs/",
            "runbook updates when operator flow changed",
        ],
        "notes": ["Behavior changes should not ship without the narrowest proof test."],
    },
    "contract-change": {
        "required_updates": [
            "OpenAPI spec in contracts/api/",
            "JSON Schema in contracts/schemas/ or contracts/events/",
            "generated clients via npm run openapi:generate in legal-search/",
            "contract tests and schema validation",
        ],
        "notes": ["Contracts live in the monorepo root contracts/ directory."],
    },
    "infra-change": {
        "required_updates": [
            "generated Terraform docs",
            "docs/setup/ guides",
            "runbook updates when deployment or recovery changed",
        ],
        "notes": ["Do not hand-maintain Terraform reference docs."],
    },
    "pipeline-change": {
        "required_updates": [
            "data quality checks",
            "pipeline docs",
            "failure-mode notes and recovery instructions",
        ],
        "notes": ["Prefer the narrowest pipeline proof rather than a broad brittle test."],
    },
    "architecture-change": {
        "required_updates": [
            "structurizr/workspace.dsl",
            "ADR in docs/adr/ for significant decisions",
            "docs/architecture/ narrative updates",
        ],
        "notes": ["Use Mermaid only in docs pages for explanation, not as the source of truth."],
    },
    "docs-only": {
        "required_updates": ["docs only"],
        "notes": ["No code changes required unless documentation drift reveals a real defect."],
    },
}

_PATH_CHECK_RULES = (
    {
        "prefixes": (
            "document-intelligence/src/document_intelligence/config/",
            "document-intelligence/src/document_intelligence/processing_runtime.py",
        ),
        "component": "document-intelligence",
        "recommended_check": "bash scripts/check-document-intelligence-runtime.sh",
        "docs": "docs/components/document-intelligence.md",
        "reason": "Runtime/config changes should prove the focused DI runtime path before the broader component check.",
    },
    {
        "prefixes": ("document-intelligence/",),
        "component": "document-intelligence",
        "recommended_check": "bash scripts/check-document-intelligence.sh",
        "docs": "docs/components/document-intelligence.md",
        "reason": "Document Intelligence changes should use the repo's shared narrow quality gate before broader integration checks.",
    },
    {
        "prefixes": ("legal-search/frontend/", "legal-search/api/", "legal-search/"),
        "component": "legal-search",
        "recommended_check": "cd legal-search && npm run check",
        "docs": "docs/components/legal-search.md",
        "reason": "Legal Search uses the workspace-wide typecheck, lint, and test gate as its standard proof.",
    },
    {
        "prefixes": ("platform-control/",),
        "component": "platform-control",
        "recommended_check": "cd platform-control && uv run pytest",
        "docs": "docs/components/platform-control.md",
        "reason": "Platform Control changes should default to the narrowest relevant pytest scope before broader smoke coverage.",
    },
    {
        "prefixes": ("contracts/api/",),
        "component": "contracts",
        "recommended_check": "cd legal-search && npm run openapi:check",
        "docs": "docs/components/contracts.md",
        "reason": "OpenAPI contract changes must prove generated-client drift stays clean.",
    },
    {
        "prefixes": ("contracts/schemas/", "contracts/events/"),
        "component": "contracts",
        "recommended_check": "python3 scripts/validate_json_schemas.py",
        "docs": "docs/components/contracts.md",
        "reason": "Schema changes should validate JSON Schema structure directly before downstream consumers.",
    },
    {
        "prefixes": ("infra/",),
        "component": "infra",
        "recommended_check": "cd infra/terraform && terraform fmt -check && terraform validate",
        "docs": "docs/components/infra.md",
        "reason": "Infra changes should keep formatting and validation aligned with Terraform as the source of truth.",
    },
)


def resolve_repo_root(raw_root: str | None = None) -> Path:
    if raw_root:
        candidate = Path(raw_root).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if (candidate / "AGENTS.md").exists():
            return candidate.resolve()

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "AGENTS.md").exists():
            return parent
    raise FileNotFoundError("Could not locate Evidara repo root from MCP server package")


def repo_overview() -> dict[str, Any]:
    return {
        "repo_name": "Evidara",
        "components": [component.__dict__ for component in _COMPONENTS.values()],
        "contract_source_of_truth": "contracts/",
        "design_tokens_source_of_truth": "legal-search/src/app/globals.css",
        "architecture_source_of_truth": "structurizr/workspace.dsl",
    }


def component_quality_gate(component: str) -> dict[str, str]:
    normalized = component.strip().lower()
    guide = _COMPONENTS.get(normalized)
    if guide is None:
        raise ValueError(f"Unknown component: {component}")
    return guide.__dict__


def narrowest_check_for_path(path: str) -> dict[str, str]:
    normalized = path.strip().lstrip("./").replace("\\", "/")
    if not normalized:
        raise ValueError("path must not be empty")

    for rule in _PATH_CHECK_RULES:
        if any(normalized.startswith(prefix) for prefix in rule["prefixes"]):
            return {
                "path": normalized,
                "component": rule["component"],
                "recommended_check": rule["recommended_check"],
                "docs": rule["docs"],
                "reason": rule["reason"],
            }

    raise ValueError(f"No Evidara quality-gate rule matches path: {path}")


def search_tree(root: Path, *, base_path: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if limit < 1:
        raise ValueError("limit must be >= 1")

    search_root = root / base_path
    if not search_root.exists():
        return []

    matches: list[dict[str, Any]] = []
    for path in sorted(search_root.rglob("*")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8", errors="ignore") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if normalized_query in line.lower():
                        matches.append(
                            {
                                "path": str(path.relative_to(root)),
                                "line": line_number,
                                "snippet": line.strip(),
                            }
                        )
                        if len(matches) >= limit:
                            return matches
        except OSError:
            continue
    return matches


def search_contracts(root: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:
    return search_tree(root, base_path="contracts", query=query, limit=limit)


def search_docs(root: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:
    return search_tree(root, base_path="docs", query=query, limit=limit)


def search_runbooks(root: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:
    return search_tree(root, base_path="docs/runbooks", query=query, limit=limit)


def change_sync_requirements(change_type: str) -> dict[str, Any]:
    normalized = change_type.strip().lower()
    requirements = _CHANGE_SYNC_REQUIREMENTS.get(normalized)
    if requirements is None:
        raise ValueError(f"Unknown change type: {change_type}")
    return {
        "change_type": normalized,
        **requirements,
    }
