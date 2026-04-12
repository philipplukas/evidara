"""DSPy extraction evaluation harness.

Runs TitleExtractor and SourceFamilyClassifier against the golden fixture
set and reports accuracy, cost, and latency metrics.

Usage:
    # With live LLM (requires credentials):
    uv run --extra llm python tests/eval_dspy_extraction.py

    # With mock LLM (CI-safe, tests harness logic only):
    uv run --extra llm python tests/eval_dspy_extraction.py --mock

    # Override provider/model:
    DI_LLM_PROVIDER=openai DI_LLM_MODEL=gpt-4o-mini uv run --extra llm python tests/eval_dspy_extraction.py

Output: JSON report to stdout, human-readable summary to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

GOLDEN_DIR = Path(__file__).parent / "golden"

# Ground truth for each fixture: (title_exact_or_contains, source_family)
# These are the canonical answers the LLM modules should produce.
EVAL_SET: list[dict[str, Any]] = [
    {
        "fixture": "simple_html",
        "expected_title": "Simple Statute",
        "expected_source_family": "law",
        "title_match": "exact",
    },
    {
        "fixture": "messy_html",
        "expected_title": "Messy Regulation",
        "expected_source_family": "law",
        "title_match": "exact",
    },
    {
        "fixture": "nested_headings",
        "expected_title": "Nested Structure Act",
        "expected_source_family": "law",
        "title_match": "exact",
    },
    {
        "fixture": "no_heading_fallback",
        "expected_title": "Fallback Order",
        "expected_source_family": "admin_guidance",
        "title_match": "exact",
    },
    {
        "fixture": "html_div_fallback",
        "expected_title": "Verordnung über Muster",
        "expected_source_family": "law",
        "title_match": "exact",
    },
    {
        "fixture": "ris_xml",
        "expected_title": "Bundesgesetz über digitale Register",
        "expected_source_family": "law",
        "title_match": "exact",
    },
    {
        "fixture": "ris_html_decision_vfgh",
        "expected_title": None,
        "expected_title_contains": "Verfassungsgerichtshof",
        "expected_source_family": "decision",
        "title_match": "contains",
    },
    {
        "fixture": "ris_html_decision_vwgh",
        "expected_title": None,
        "expected_title_contains": "Verwaltungsgerichtshof",
        "expected_source_family": "decision",
        "title_match": "contains",
    },
    {
        "fixture": "ris_xml_decision_vfgh",
        "expected_title": None,
        "expected_title_contains": "Verfassungsgerichtshof",
        "expected_source_family": "decision",
        "title_match": "contains",
    },
    {
        "fixture": "ris_xml_decision_vwgh",
        "expected_title": None,
        "expected_title_contains": "Verwaltungsgerichtshof",
        "expected_source_family": "decision",
        "title_match": "contains",
    },
    {
        "fixture": "ris_xml_law_consolidated",
        "expected_title": None,
        "expected_title_contains": "Bundesnorm",
        "expected_source_family": "law",
        "title_match": "contains",
    },
    {
        "fixture": "ris_xml_law_short",
        "expected_title": None,
        "expected_title_contains": "Notarstelle",
        "expected_source_family": "law",
        "title_match": "contains",
    },
]


@dataclass
class EvalResult:
    fixture: str
    title_correct: bool
    title_predicted: str
    title_expected: str
    title_confidence: float
    family_correct: bool
    family_predicted: str
    family_expected: str
    family_confidence: float
    latency_ms: float
    error: str | None = None


@dataclass
class EvalReport:
    provider: str
    model: str
    total: int
    title_correct: int
    title_accuracy: float
    family_correct: int
    family_accuracy: float
    avg_latency_ms: float
    p95_latency_ms: float
    results: list[EvalResult] = field(default_factory=list)


def load_document_text(fixture_name: str) -> str:
    """Load the primary artifact text from a golden fixture."""
    fixture_dir = GOLDEN_DIR / fixture_name
    for candidate in ["document.html", "document.xml", "document.json"]:
        path = fixture_dir / candidate
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"No artifact in {fixture_dir}")


def load_metadata_hints(fixture_name: str) -> dict[str, Any]:
    """Load manifest metadata hints for LLM context."""
    manifest_path = GOLDEN_DIR / fixture_name / "bundle-manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hints: dict[str, Any] = {}
    provenance = manifest.get("provenance", {})
    if provenance.get("source_defaults"):
        hints["source_defaults"] = provenance["source_defaults"]
    di_overrides = manifest.get("di_overrides")
    if di_overrides:
        hints["di_overrides"] = di_overrides
    return hints


def evaluate_fixture(
    fixture_spec: dict[str, Any],
    title_extractor: Any,
    classifier: Any,
) -> EvalResult:
    """Evaluate a single fixture against both modules."""
    fixture_name = fixture_spec["fixture"]
    doc_text = load_document_text(fixture_name)
    hints = load_metadata_hints(fixture_name)

    start = time.perf_counter()
    error = None

    try:
        title_result = title_extractor.extract(doc_text, hints)
        family_result = classifier.classify(doc_text, hints)
    except Exception as exc:
        error = str(exc)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return EvalResult(
            fixture=fixture_name,
            title_correct=False,
            title_predicted="",
            title_expected=fixture_spec.get("expected_title") or fixture_spec.get("expected_title_contains", ""),
            title_confidence=0.0,
            family_correct=False,
            family_predicted="",
            family_expected=fixture_spec["expected_source_family"],
            family_confidence=0.0,
            latency_ms=elapsed_ms,
            error=error,
        )

    elapsed_ms = (time.perf_counter() - start) * 1000

    predicted_title = title_result.get("title", "")
    title_confidence = title_result.get("confidence", 0.0)

    match_mode = fixture_spec.get("title_match", "exact")
    if match_mode == "exact":
        title_correct = predicted_title.strip() == (fixture_spec.get("expected_title") or "").strip()
    else:
        needle = fixture_spec.get("expected_title_contains", "")
        title_correct = needle.lower() in predicted_title.lower() if needle else True

    predicted_family = family_result.get("source_family", "unknown")
    family_confidence = family_result.get("confidence", 0.0)
    family_correct = predicted_family == fixture_spec["expected_source_family"]

    title_needle = fixture_spec.get("expected_title_contains", "")
    expected_title_display = fixture_spec.get("expected_title") or f"*contains* {title_needle}"

    return EvalResult(
        fixture=fixture_name,
        title_correct=title_correct,
        title_predicted=predicted_title,
        title_expected=expected_title_display,
        title_confidence=title_confidence,
        family_correct=family_correct,
        family_predicted=predicted_family,
        family_expected=fixture_spec["expected_source_family"],
        family_confidence=family_confidence,
        latency_ms=elapsed_ms,
        error=error,
    )


def run_eval(use_mock: bool = False) -> EvalReport:
    """Run the full evaluation and return a report."""
    from document_intelligence.extractors.profile_config import ExtractionProfileConfig

    profile = ExtractionProfileConfig.from_environment()

    if use_mock:
        from unittest.mock import MagicMock, patch

        with patch("dspy.configure"):
            from document_intelligence.extractors.dspy_modules import (
                SourceFamilyClassifier,
                TitleExtractor,
            )

            title_ext = MagicMock()
            classifier = MagicMock()

            title_ext.extract = lambda text, hints=None: {
                "title": text[:50].split("<")[0].strip() or "Mock Title",
                "confidence": 0.5,
            }
            classifier.classify = lambda text, hints=None: {
                "source_family": "law",
                "confidence": 0.5,
            }
    else:
        import dspy

        from document_intelligence.extractors.dspy_modules import (
            SourceFamilyClassifier,
            TitleExtractor,
        )

        provider_prefixes = {
            "vertexai": "vertex_ai",
            "vertex_ai": "vertex_ai",
            "gemini": "gemini",
            "openai": "openai",
        }
        prefix = provider_prefixes.get(profile.llm_provider)
        if prefix is None:
            raise ValueError(f"Unsupported provider: {profile.llm_provider}")
        lm = dspy.LM(f"{prefix}/{profile.llm_model}")
        dspy.configure(lm=lm)

        title_ext = TitleExtractor()
        classifier = SourceFamilyClassifier()

    results: list[EvalResult] = []
    for spec in EVAL_SET:
        result = evaluate_fixture(spec, title_ext, classifier)
        results.append(result)
        status = "OK" if (result.title_correct and result.family_correct) else "FAIL"
        print(
            f"  [{status}] {result.fixture}: "
            f"title={'Y' if result.title_correct else 'N'}({result.title_confidence:.2f}) "
            f"family={'Y' if result.family_correct else 'N'}({result.family_confidence:.2f}) "
            f"{result.latency_ms:.0f}ms",
            file=sys.stderr,
        )

    latencies = [r.latency_ms for r in results if r.error is None]
    sorted_latencies = sorted(latencies) if latencies else [0]
    p95_idx = int(len(sorted_latencies) * 0.95)
    p95_latency = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]

    title_correct = sum(1 for r in results if r.title_correct)
    family_correct = sum(1 for r in results if r.family_correct)
    total = len(results)

    report = EvalReport(
        provider=profile.llm_provider,
        model=profile.llm_model,
        total=total,
        title_correct=title_correct,
        title_accuracy=title_correct / total if total else 0,
        family_correct=family_correct,
        family_accuracy=family_correct / total if total else 0,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0,
        p95_latency_ms=p95_latency,
        results=results,
    )

    return report


@dataclass
class CascadeEvalResult:
    fixture: str
    title_correct: bool
    title_predicted: str
    title_expected: str
    title_source: str
    family_correct: bool
    family_predicted: str
    family_expected: str
    family_source: str
    llm_invoked: bool
    latency_ms: float
    error: str | None = None


@dataclass
class CascadeEvalReport:
    total: int
    title_correct: int
    title_accuracy: float
    family_correct: int
    family_accuracy: float
    llm_invoked_count: int
    llm_skip_rate: float
    avg_latency_ms: float
    results: list[CascadeEvalResult] = field(default_factory=list)


def run_cascade_eval(use_mock: bool = False) -> CascadeEvalReport:
    """Evaluate the full cascade pipeline: structured extraction + conditional LLM."""
    from support import fixture_path

    results: list[CascadeEvalResult] = []

    for spec in EVAL_SET:
        fixture_name = spec["fixture"]
        fixture_dir = fixture_path("golden", fixture_name)

        doc_file = None
        content_type = "text/html"
        for candidate, ct in [
            ("document.xml", "application/xml"),
            ("document.html", "text/html"),
            ("document.json", "application/json"),
        ]:
            candidate_path = os.path.join(fixture_dir, candidate)
            if os.path.exists(candidate_path):
                doc_file = candidate_path
                content_type = ct
                break

        if doc_file is None:
            results.append(
                CascadeEvalResult(
                    fixture=fixture_name,
                    title_correct=False,
                    title_predicted="",
                    title_expected=spec.get("expected_title") or spec.get("expected_title_contains", ""),
                    title_source="none",
                    family_correct=False,
                    family_predicted="",
                    family_expected=spec["expected_source_family"],
                    family_source="none",
                    llm_invoked=False,
                    latency_ms=0,
                    error="no_fixture_file",
                )
            )
            continue

        import tempfile

        from document_intelligence.pipeline import ProcessingPipeline
        from support import build_bundle_event, build_manifest_payload

        manifest_data = build_manifest_payload(
            doc_file,
            artifact_role="primary_document",
            content_type=content_type,
        )
        # Remove hints to test cascade's own extraction
        if use_mock:
            manifest_data["source_defaults"].pop("document_type_hint", None)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as mf:
            json.dump(manifest_data, mf)
            manifest_path = mf.name

        start = time.perf_counter()
        try:
            result = ProcessingPipeline(
                processing_version="di_cascade_eval",
            ).process_event(build_bundle_event(manifest_path))
            elapsed_ms = (time.perf_counter() - start) * 1000

            predicted_title = result.document.title or ""
            predicted_type = result.document.document_type or ""
            fp = result.document.metadata.get("field_provenance", {})
            title_source = fp.get("title", {}).get("source", "unknown")
            sf_src = fp.get("source_family", {}).get("source")
            dt_src = fp.get("document_type", {}).get("source")
            family_source = sf_src or dt_src or "unknown"
            predicted_family = fp.get("source_family", {}).get("value", predicted_type)

            llm_meta = result.document.metadata.get("llm_extraction", {})
            llm_invoked = bool(llm_meta.get("llm_invoked", False))

            match_mode = spec.get("title_match", "exact")
            if match_mode == "exact":
                title_correct = predicted_title.strip() == (spec.get("expected_title") or "").strip()
            else:
                needle = spec.get("expected_title_contains", "")
                title_correct = needle.lower() in predicted_title.lower() if needle else True

            family_correct = predicted_family == spec["expected_source_family"]
            cascade_title_needle = spec.get("expected_title_contains", "")
            expected_title_display = spec.get("expected_title") or f"*contains* {cascade_title_needle}"

            results.append(
                CascadeEvalResult(
                    fixture=fixture_name,
                    title_correct=title_correct,
                    title_predicted=predicted_title,
                    title_expected=expected_title_display,
                    title_source=title_source,
                    family_correct=family_correct,
                    family_predicted=predicted_family,
                    family_expected=spec["expected_source_family"],
                    family_source=family_source,
                    llm_invoked=llm_invoked,
                    latency_ms=elapsed_ms,
                )
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            results.append(
                CascadeEvalResult(
                    fixture=fixture_name,
                    title_correct=False,
                    title_predicted="",
                    title_expected=spec.get("expected_title") or spec.get("expected_title_contains", ""),
                    title_source="error",
                    family_correct=False,
                    family_predicted="",
                    family_expected=spec["expected_source_family"],
                    family_source="error",
                    llm_invoked=False,
                    latency_ms=elapsed_ms,
                    error=str(exc),
                )
            )
        finally:
            os.unlink(manifest_path)

    total = len(results)
    title_correct = sum(1 for r in results if r.title_correct)
    family_correct = sum(1 for r in results if r.family_correct)
    llm_invoked_count = sum(1 for r in results if r.llm_invoked)
    latencies = [r.latency_ms for r in results if r.error is None]

    return CascadeEvalReport(
        total=total,
        title_correct=title_correct,
        title_accuracy=title_correct / total if total else 0,
        family_correct=family_correct,
        family_accuracy=family_correct / total if total else 0,
        llm_invoked_count=llm_invoked_count,
        llm_skip_rate=1.0 - (llm_invoked_count / total) if total else 0,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0,
        results=results,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="DSPy extraction eval harness")
    parser.add_argument("--mock", action="store_true", help="Use mock LLM (CI-safe)")
    parser.add_argument(
        "--cascade",
        action="store_true",
        help="Evaluate full cascade pipeline (structured + conditional LLM)",
    )
    parser.add_argument("--output", type=str, default=None, help="Write JSON report to file")
    args = parser.parse_args()

    if args.cascade:
        print(f"Cascade Extraction Eval — {len(EVAL_SET)} fixtures", file=sys.stderr)
        print(f"  Mock: {args.mock}", file=sys.stderr)
        print("", file=sys.stderr)

        report = run_cascade_eval(use_mock=args.mock)

        for r in report.results:
            status = "OK" if (r.title_correct and r.family_correct) else "FAIL"
            llm_tag = "LLM" if r.llm_invoked else "SKIP"
            print(
                f"  [{status}] {r.fixture}: "
                f"title={'Y' if r.title_correct else 'N'}({r.title_source}) "
                f"family={'Y' if r.family_correct else 'N'}({r.family_source}) "
                f"[{llm_tag}] {r.latency_ms:.0f}ms",
                file=sys.stderr,
            )

        print("", file=sys.stderr)
        tc, tot = report.title_correct, report.total
        print(f"Title accuracy:    {tc}/{tot} = {report.title_accuracy:.1%}", file=sys.stderr)
        fc = report.family_correct
        print(f"Family accuracy:   {fc}/{tot} = {report.family_accuracy:.1%}", file=sys.stderr)
        skipped = tot - report.llm_invoked_count
        skip_msg = f"LLM skip rate:     {report.llm_skip_rate:.1%} ({skipped}/{tot} skipped)"
        print(skip_msg, file=sys.stderr)
        print(f"Avg latency:       {report.avg_latency_ms:.0f}ms", file=sys.stderr)

        report_dict = asdict(report)
        report_json = json.dumps(report_dict, indent=2, default=str)

        if args.output:
            Path(args.output).write_text(report_json, encoding="utf-8")
            print(f"Report written to {args.output}", file=sys.stderr)
        else:
            print(report_json)
        return

    print(f"DSPy Extraction Eval — {len(EVAL_SET)} fixtures", file=sys.stderr)
    print(f"  Provider: {os.environ.get('DI_LLM_PROVIDER', 'vertexai')}", file=sys.stderr)
    print(f"  Model:    {os.environ.get('DI_LLM_MODEL', 'gemini-2.0-flash')}", file=sys.stderr)
    print(f"  Mock:     {args.mock}", file=sys.stderr)
    print("", file=sys.stderr)

    report = run_eval(use_mock=args.mock)

    print("", file=sys.stderr)
    print(f"Title accuracy:  {report.title_correct}/{report.total} = {report.title_accuracy:.1%}", file=sys.stderr)
    print(f"Family accuracy: {report.family_correct}/{report.total} = {report.family_accuracy:.1%}", file=sys.stderr)
    print(f"Avg latency:     {report.avg_latency_ms:.0f}ms", file=sys.stderr)
    print(f"P95 latency:     {report.p95_latency_ms:.0f}ms", file=sys.stderr)

    if report.title_accuracy >= 0.9:
        print("PASS: TitleExtractor >= 90% accuracy", file=sys.stderr)
    else:
        print(f"FAIL: TitleExtractor {report.title_accuracy:.1%} < 90% target", file=sys.stderr)

    if report.family_accuracy >= 1.0:
        print("PASS: SourceFamilyClassifier correct on all fixtures", file=sys.stderr)
    else:
        failed = [r for r in report.results if not r.family_correct]
        print(
            f"FAIL: SourceFamilyClassifier missed {len(failed)}: "
            + ", ".join(f"{r.fixture}({r.family_predicted}!={r.family_expected})" for r in failed),
            file=sys.stderr,
        )

    report_dict = asdict(report)
    report_json = json.dumps(report_dict, indent=2, default=str)

    if args.output:
        Path(args.output).write_text(report_json, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report_json)


if __name__ == "__main__":
    main()
