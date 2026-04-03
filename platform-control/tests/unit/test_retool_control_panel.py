from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
RETOOL_ROOT = REPO_ROOT / "platform-control" / "retool"
MANIFEST_PATH = RETOOL_ROOT / "control-panel.manifest.yaml"
OPENAPI_PATH = REPO_ROOT / "contracts" / "api" / "platform-control.openapi.yaml"
_TEMPLATE_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _normalize_action_path(path: str) -> str:
    return _TEMPLATE_PATTERN.sub(r"{\1}", path)


def test_control_panel_manifest_references_existing_files_and_routes() -> None:
    manifest = _load_yaml(MANIFEST_PATH)
    openapi = _load_yaml(OPENAPI_PATH)
    openapi_paths = openapi["paths"]

    assert manifest["workflow"]["file"] == "workflows/run_firecrawl_preview.yaml"
    assert manifest["agent"]["file"] == "agents/source-setup-copilot.md"
    assert (RETOOL_ROOT / manifest["workflow"]["file"]).exists()
    assert (RETOOL_ROOT / manifest["agent"]["file"]).exists()

    for page in manifest["pages"]:
        for read_path in page.get("reads", []):
            assert (RETOOL_ROOT / read_path).exists(), read_path

    for action_name, action in manifest["actions"].items():
        normalized_path = _normalize_action_path(action["path"])
        method = action["method"].lower()
        assert normalized_path in openapi_paths, action_name
        assert method in openapi_paths[normalized_path], action_name


def test_control_panel_manifest_covers_demo_run_detail_flow() -> None:
    manifest = _load_yaml(MANIFEST_PATH)
    pages = {page["id"]: page for page in manifest["pages"]}

    assert "run-detail" in pages
    assert pages["sources"]["detail"]["fields"] == ["extractor_profile_id", "acquisition_spec"]
    assert pages["preview-review"]["links"] == ["run-detail"]
    assert pages["runs"]["links"] == ["run-detail"]
    assert pages["runs"]["filters"] == [
        {
            "field": "mode",
            "label": "Run mode",
            "options": ["preview", "production"],
        }
    ]
    assert pages["runs"]["actions"][0] == "createRun"
    assert pages["run-detail"]["reads"] == [
        "sql/list_run_captured_resources.sql",
        "sql/list_run_provider_jobs.sql",
        "sql/list_run_raw_artifacts.sql",
    ]
    assert pages["run-detail"]["actions"] == [
        "getRun",
        "getRunPreviewSummary",
        "listRunProcessingStatus",
        "listRunDocumentLifecycle",
        "cancelRun",
    ]
