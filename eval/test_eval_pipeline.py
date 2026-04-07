"""Pipeline integration tests using real RIS content.

Runs documents through the DI ProcessingPipeline and validates output
against golden expectations. This does NOT test search/retrieval —
it tests the ingestion + normalization + sectionization path.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).parent
GOLDEN_DIR = EVAL_DIR.parent / "document-intelligence" / "tests" / "golden"

_RIS_FIXTURES = [
    "ris_xml_law_short",
    "ris_xml_law_consolidated",
    "ris_xml_decision_vfgh",
    "ris_xml_decision_vwgh",
    "ris_html_decision_vfgh",
    "ris_html_decision_vwgh",
]


def _fixture_dirs() -> list[Path]:
    return [GOLDEN_DIR / name for name in _RIS_FIXTURES if (GOLDEN_DIR / name).is_dir()]


def _materialize_fixture(fixture_dir: Path, work_dir: Path) -> dict[str, Any]:
    """Copy fixture to work_dir and replace path/size/checksum placeholders."""
    artifact_candidates = list(fixture_dir.glob("document.*"))
    if not artifact_candidates:
        pytest.skip(f"No document artifact in {fixture_dir}")
    artifact_src = artifact_candidates[0]
    artifact_dest = work_dir / artifact_src.name
    shutil.copy2(artifact_src, artifact_dest)

    artifact_bytes = artifact_dest.read_bytes()
    artifact_checksum = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_size = len(artifact_bytes)

    manifest_src = fixture_dir / "bundle-manifest.json"
    manifest_text = manifest_src.read_text(encoding="utf-8")
    manifest_text = manifest_text.replace("__ARTIFACT_PATH__", str(artifact_dest))
    manifest_text = manifest_text.replace("__ARTIFACT_SIZE__", str(artifact_size))
    manifest_text = manifest_text.replace('"__ARTIFACT_SIZE__"', str(artifact_size))
    manifest_text = manifest_text.replace("__ARTIFACT_CHECKSUM__", artifact_checksum)
    manifest_dest = work_dir / "bundle-manifest.json"
    manifest_dest.write_text(manifest_text, encoding="utf-8")

    manifest_bytes = manifest_dest.read_bytes()
    manifest_checksum = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_size = len(manifest_bytes)

    event_src = fixture_dir / "event.json"
    event_text = event_src.read_text(encoding="utf-8")
    event_text = event_text.replace("__MANIFEST_PATH__", str(manifest_dest))
    event_text = event_text.replace("__MANIFEST_SIZE__", str(manifest_size))
    event_text = event_text.replace('"__MANIFEST_SIZE__"', str(manifest_size))
    event_text = event_text.replace("__MANIFEST_CHECKSUM__", manifest_checksum)
    event_dest = work_dir / "event.json"
    event_dest.write_text(event_text, encoding="utf-8")

    expected = {}
    expected_path = fixture_dir / "expected.json"
    if expected_path.exists():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))

    return {
        "event_path": event_dest,
        "manifest_path": manifest_dest,
        "artifact_path": artifact_dest,
        "expected": expected,
        "fixture_name": fixture_dir.name,
    }


def _try_import_pipeline():
    """Attempt to import the DI ProcessingPipeline; skip if unavailable."""
    try:
        from document_intelligence.pipeline import ProcessingPipeline
        return ProcessingPipeline
    except ImportError:
        pytest.skip("document_intelligence not installed in this environment")


@pytest.mark.parametrize("fixture_name", _RIS_FIXTURES)
def test_ris_fixture_processing(fixture_name: str) -> None:
    """Process a real RIS golden fixture through the pipeline."""
    ProcessingPipeline = _try_import_pipeline()

    fixture_dir = GOLDEN_DIR / fixture_name
    if not fixture_dir.is_dir():
        pytest.skip(f"Fixture {fixture_name} not found at {fixture_dir}")

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        materialized = _materialize_fixture(fixture_dir, work_dir)

        event_data = json.loads(materialized["event_path"].read_text(encoding="utf-8"))
        expected = materialized["expected"]

        pipeline = ProcessingPipeline()
        result = pipeline.process_event(event_data)

        assert result.document is not None, f"Pipeline returned no document for {fixture_name}"
        assert result.document.title, f"Document has no title for {fixture_name}"

        if "title_contains" in expected:
            assert expected["title_contains"].lower() in result.document.title.lower(), (
                f"Title '{result.document.title}' does not contain '{expected['title_contains']}'"
            )

        if "section_count_min" in expected:
            assert len(result.sections) >= expected["section_count_min"], (
                f"Expected >= {expected['section_count_min']} sections, "
                f"got {len(result.sections)} for {fixture_name}"
            )

        if "key_content_contains" in expected:
            full_text = result.document.full_text or ""
            for keyword in expected["key_content_contains"]:
                assert keyword.lower() in full_text.lower(), (
                    f"Full text missing keyword '{keyword}' for {fixture_name}"
                )

        if "source_flavor" in expected:
            actual_flavor = result.document.metadata.get("source_flavor", "")
            assert actual_flavor == expected["source_flavor"], (
                f"Expected source_flavor='{expected['source_flavor']}', "
                f"got '{actual_flavor}' for {fixture_name}"
            )

        if "status_flow" in expected:
            statuses = [e.get("payload", {}).get("status") for e in
                       [json.loads(json.dumps(se)) if isinstance(se, dict) else {}
                        for se in (result.status_events or [])]]
            # Status events are dicts with nested payload, extract the status string
            actual_statuses = []
            for se in result.status_events or []:
                if hasattr(se, "get"):
                    actual_statuses.append(se.get("payload", {}).get("status", ""))
                elif hasattr(se, "payload"):
                    payload = se.payload if hasattr(se, "payload") else {}
                    if hasattr(payload, "get"):
                        actual_statuses.append(payload.get("status", ""))

            for expected_status in expected["status_flow"]:
                assert any(expected_status in str(s) for s in actual_statuses + statuses), (
                    f"Expected status '{expected_status}' not found in flow for {fixture_name}"
                )


def test_eval_data_integrity(
    documents_catalog: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    gold_answers: dict[str, dict[str, Any]],
) -> None:
    """Verify referential integrity across eval CSV files."""
    doc_ids = {d["doc_id"] for d in documents_catalog}
    query_ids = {q["query_id"] for q in queries}

    assert len(doc_ids) >= 10, f"Expected >= 10 documents, got {len(doc_ids)}"
    assert len(query_ids) >= 20, f"Expected >= 20 queries, got {len(query_ids)}"
    assert query_ids == set(gold_answers.keys()), (
        f"Query IDs don't match gold answer IDs: "
        f"missing_gold={query_ids - set(gold_answers.keys())}, "
        f"extra_gold={set(gold_answers.keys()) - query_ids}"
    )

    for qid, gold in gold_answers.items():
        required = {d.strip() for d in (gold.get("required_doc_ids") or "").split("|") if d.strip()}
        missing = required - doc_ids
        assert not missing, f"Gold answer {qid} references unknown doc_ids: {missing}"


def test_query_task_type_coverage(queries: list[dict[str, Any]]) -> None:
    """Verify all task types have at least 3 queries."""
    task_counts: dict[str, int] = {}
    for q in queries:
        task_type = q.get("task_type", "unknown")
        task_counts[task_type] = task_counts.get(task_type, 0) + 1

    expected_tasks = {
        "section_extraction",
        "holding_extraction",
        "temporal_version",
        "source_classification",
        "citation_chain",
        "cross_reference",
    }
    assert expected_tasks <= set(task_counts.keys()), (
        f"Missing task types: {expected_tasks - set(task_counts.keys())}"
    )
    for task, count in task_counts.items():
        assert count >= 3, f"Task type '{task}' has only {count} queries (need >= 3)"
