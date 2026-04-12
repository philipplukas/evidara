"""Pytest wrapper for Docling DocumentExtractor evaluation spike.

Runs mock eval in CI; live eval when DI_EVAL_DOCLING=1 is set.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from eval_docling_extractor import EVAL_FIXTURES, LegalDocumentSchema, run_eval

LIVE = os.environ.get("DI_EVAL_DOCLING", "").strip().lower() in {"1", "true", "yes"}


def test_legal_document_schema_validates():
    """Pydantic schema accepts valid legal document metadata."""
    m = LegalDocumentSchema(
        title="Test Law",
        document_type="law",
        court_name=None,
        decision_date=None,
    )
    assert m.title == "Test Law"
    assert m.document_type == "law"


def test_eval_harness_runs_mock():
    """Eval harness runs with mock extraction."""
    report = run_eval(use_mock=True)
    assert report.total == len(EVAL_FIXTURES)
    assert report.successful == report.total
    assert report.avg_latency_ms >= 0


@pytest.mark.skipif(not LIVE, reason="DI_EVAL_DOCLING not set — skipping live Docling eval")
def test_docling_extractor_live():
    """Spike: Docling DocumentExtractor with Pydantic schema on golden fixtures."""
    report = run_eval(use_mock=False)
    assert report.total > 0
    for r in report.results:
        if not r.success:
            print(f"  FAIL {r.fixture}: {r.error}")
    assert report.successful >= 1, f"Expected at least 1 successful extraction, got {report.successful}"
