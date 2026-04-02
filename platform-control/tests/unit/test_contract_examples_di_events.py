"""Ensure canonical contract examples parse with platform-control event models."""

from __future__ import annotations

from pathlib import Path

from platform_control.schemas.document_events import DocumentProcessedEvent, DocumentWithdrawnEvent


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_document_processed_example_matches_pydantic() -> None:
    path = _repo_root() / "contracts" / "examples" / "document-processed.json"
    DocumentProcessedEvent.model_validate_json(path.read_text(encoding="utf-8"))


def test_document_withdrawn_example_matches_pydantic() -> None:
    path = _repo_root() / "contracts" / "examples" / "document-withdrawn.json"
    DocumentWithdrawnEvent.model_validate_json(path.read_text(encoding="utf-8"))
