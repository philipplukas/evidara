from pathlib import Path

from evidara_zed_mcp.catalog import (
    change_sync_requirements,
    component_quality_gate,
    narrowest_check_for_path,
    repo_overview,
    resolve_repo_root,
    search_tree,
)


def test_component_quality_gate_returns_known_component() -> None:
    guide = component_quality_gate("document-intelligence")
    assert guide["path"] == "document-intelligence/"
    assert "check-document-intelligence.sh" in guide["quality_gate"]


def test_repo_overview_lists_core_components() -> None:
    overview = repo_overview()
    component_names = {component["name"] for component in overview["components"]}
    assert "platform-control" in component_names
    assert "legal-search" in component_names


def test_change_sync_requirements_returns_contract_change_expectations() -> None:
    requirements = change_sync_requirements("contract-change")
    assert requirements["change_type"] == "contract-change"
    assert "OpenAPI spec in contracts/api/" in requirements["required_updates"]


def test_narrowest_check_for_path_uses_component_gate_for_di_runtime_files() -> None:
    recommendation = narrowest_check_for_path(
        "document-intelligence/src/document_intelligence/processing_runtime.py"
    )

    assert recommendation["component"] == "document-intelligence"
    assert recommendation["recommended_check"] == "bash scripts/check-document-intelligence.sh"


def test_narrowest_check_for_path_uses_schema_validation_for_contract_schema_files() -> None:
    recommendation = narrowest_check_for_path("contracts/schemas/document.schema.json")

    assert recommendation["component"] == "contracts"
    assert recommendation["recommended_check"] == "python3 scripts/validate_json_schemas.py"


def test_resolve_repo_root_accepts_relative_root(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "AGENTS.md").write_text("# test\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    resolved = resolve_repo_root("repo")

    assert resolved == repo_root.resolve()


def test_search_tree_returns_matching_lines(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir(parents=True)
    target = docs_root / "example.md"
    target.write_text("hello evidara\nsecond line\n", encoding="utf-8")

    matches = search_tree(tmp_path, base_path="docs", query="evidara", limit=5)

    assert matches == [
        {
            "path": "docs/example.md",
            "line": 1,
            "snippet": "hello evidara",
        }
    ]
