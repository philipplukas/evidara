from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from evidara_cli.openapi_cmd import list_paths, list_tags


def test_list_paths_writes_sorted_paths(tmp_path: Path, capsys: object) -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {"/b": {}, "/a": {}},
    }
    contracts = tmp_path / "contracts" / "api"
    contracts.mkdir(parents=True)
    (contracts / "platform-control.openapi.yaml").write_text(
        yaml.dump(spec),
        encoding="utf-8",
    )

    with patch("typer.echo") as echo:
        list_paths("platform-control", repo_root=tmp_path)

    lines = [c.args[0] for c in echo.call_args_list if c.args]
    assert lines == ["/a", "/b"]


def test_list_tags_collects_unique_tags(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/x": {
                "get": {"tags": ["alpha", "beta"], "responses": {"200": {"description": "ok"}}},
                "post": {"tags": ["beta"], "responses": {"200": {"description": "ok"}}},
            }
        },
    }
    contracts = tmp_path / "contracts" / "api"
    contracts.mkdir(parents=True)
    (contracts / "legal-search.openapi.yaml").write_text(
        yaml.dump(spec),
        encoding="utf-8",
    )

    with patch("typer.echo") as echo:
        list_tags("legal-search", repo_root=tmp_path)

    lines = [c.args[0] for c in echo.call_args_list if c.args]
    assert lines == ["alpha", "beta"]
