"""Pytest wrapper for the DSPy extraction eval harness.

In CI (default): runs with mock LLM — validates the harness plumbing. This is
now true. It was not until #685: the mock test was guarded on `dspy` being
importable, and no CI job installed the `llm` extra, so the one test this
docstring advertised skipped on every run while the docstring claimed coverage.
CI installs `llm` as of #685 — see scripts/check-document-intelligence.sh.

With live LLM:   DI_EVAL_LIVE=1 pytest tests/test_eval_dspy_extraction.py
"""

from __future__ import annotations

import os

import pytest

from eval_dspy_extraction import EVAL_SET, run_cascade_eval, run_eval

LIVE = os.environ.get("DI_EVAL_LIVE", "").strip().lower() in {"1", "true", "yes"}


def test_eval_harness_runs_mock():
    """Eval harness runs successfully with mock LLM."""
    report = run_eval(use_mock=True)
    assert report.total == len(EVAL_SET)
    assert report.avg_latency_ms >= 0


def test_cascade_eval_runs():
    """Cascade eval harness runs against golden fixtures without LLM."""
    report = run_cascade_eval(use_mock=True)
    assert report.total == len(EVAL_SET)
    assert report.avg_latency_ms >= 0
    # All RIS XML fixtures should have source_family resolved by structured extraction
    ris_xml_results = [r for r in report.results if r.fixture.startswith("ris_xml")]
    for r in ris_xml_results:
        assert r.family_source == "structured", f"{r.fixture}: expected structured source_family, got {r.family_source}"
        assert r.family_correct, f"{r.fixture}: family_predicted={r.family_predicted} != {r.family_expected}"


def test_cascade_ris_xml_family_accuracy():
    """Cascade pipeline deterministically classifies all RIS XML fixtures correctly."""
    report = run_cascade_eval(use_mock=True)
    ris_xml_results = [r for r in report.results if r.fixture.startswith("ris_xml")]
    ris_correct = sum(1 for r in ris_xml_results if r.family_correct)
    failed_ris = [(r.fixture, r.family_predicted, r.family_expected) for r in ris_xml_results if not r.family_correct]
    assert ris_correct == len(ris_xml_results), (
        f"RIS XML family accuracy: {ris_correct}/{len(ris_xml_results)}. Failed: {failed_ris}"
    )


def test_cascade_llm_skip_rate_for_structured_fixtures():
    """Structured XML fixtures should not invoke the LLM."""
    report = run_cascade_eval(use_mock=True)
    ris_xml_results = [r for r in report.results if r.fixture.startswith("ris_xml")]
    for r in ris_xml_results:
        assert not r.llm_invoked, f"{r.fixture}: LLM should not be invoked for structured XML"


@pytest.mark.skipif(not LIVE, reason="DI_EVAL_LIVE not set — skipping live LLM eval")
def test_title_extractor_accuracy_live():
    """TAR-141 gate: TitleExtractor >= 90% accuracy on golden fixtures."""
    report = run_eval(use_mock=False)
    assert report.title_accuracy >= 0.9, (
        f"TitleExtractor accuracy {report.title_accuracy:.1%} < 90% target. "
        f"Failed: {[r.fixture for r in report.results if not r.title_correct]}"
    )


@pytest.mark.skipif(not LIVE, reason="DI_EVAL_LIVE not set — skipping live LLM eval")
def test_source_family_classifier_live():
    """TAR-141 gate: SourceFamilyClassifier correct on 12-doc eval set."""
    report = run_eval(use_mock=False)
    failed = [(r.fixture, r.family_predicted, r.family_expected) for r in report.results if not r.family_correct]
    assert report.family_accuracy >= 1.0, (
        f"SourceFamilyClassifier accuracy {report.family_accuracy:.1%}. Failed: {failed}"
    )


@pytest.mark.skipif(not LIVE, reason="DI_EVAL_LIVE not set — skipping live LLM eval")
def test_latency_baseline_live():
    """TAR-141 documentation: capture p95 latency baseline."""
    report = run_eval(use_mock=False)
    assert report.p95_latency_ms > 0
    print(f"\nBaseline — p95 latency: {report.p95_latency_ms:.0f}ms, avg: {report.avg_latency_ms:.0f}ms")
