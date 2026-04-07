from __future__ import annotations

from pathlib import Path

from evidara_cli.repo_root import resolve_repo_root


def test_resolve_repo_root_finds_ancestor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "contracts" / "api").mkdir(parents=True)
    nested = repo / "tools" / "evidara-cli"
    nested.mkdir(parents=True)
    assert resolve_repo_root(nested) == repo


def test_resolve_repo_root_explicit_without_marker_returns_path(tmp_path: Path) -> None:
    leaf = tmp_path / "a" / "b"
    leaf.mkdir(parents=True)
    assert resolve_repo_root(leaf) == leaf.resolve()
