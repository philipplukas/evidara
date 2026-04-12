"""Evaluation spike: Docling DocumentExtractor with Pydantic legal schema.

Tests whether Docling's DocumentExtractor can extract structured legal metadata
from documents using a Pydantic schema template. This spike evaluates the
PDF/image extraction path as an alternative to the text+LLM approach.

Usage:
    # Run with mock (CI-safe, tests schema and plumbing):
    uv run python tests/eval_docling_extractor.py --mock

    # Run live against golden fixtures (requires docling installed):
    uv run python tests/eval_docling_extractor.py
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from support import fixture_path


class LegalDocumentSchema(BaseModel):
    """Pydantic schema for Docling DocumentExtractor template."""

    title: str = Field(description="Canonical title of the legal document", examples=["Bundesgesetz ueber..."])
    document_type: str = Field(
        description="Type: law, decision, commentary, admin_guidance, unknown",
        examples=["law", "decision"],
    )
    court_name: str | None = Field(
        default=None,
        description="Court name if decision",
        examples=["Verfassungsgerichtshof"],
    )
    decision_date: str | None = Field(
        default=None,
        description="Decision date if applicable",
        examples=["2026-01-15"],
    )
    publication_reference: str | None = Field(
        default=None,
        description="BGBl or other publication reference",
    )


@dataclass
class ExtractorResult:
    fixture: str
    success: bool
    extracted: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class EvalReport:
    results: list[ExtractorResult]
    total: int = 0
    successful: int = 0
    avg_latency_ms: float = 0.0

    def __post_init__(self):
        self.total = len(self.results)
        self.successful = sum(1 for r in self.results if r.success)
        latencies = [r.latency_ms for r in self.results if r.success]
        self.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0


# Fixtures with document files that Docling can process
EVAL_FIXTURES = [
    "simple_html",
    "messy_html",
    "nested_headings",
    "ris_xml_law_consolidated",
]


def _find_fixture_file(fixture_name: str) -> str | None:
    """Find a document file in the fixture directory."""
    fixture_dir = fixture_path("golden", fixture_name)
    for name in ("document.html", "document.xml", "document.pdf"):
        path = os.path.join(fixture_dir, name)
        if os.path.exists(path):
            return path
    return None


def run_eval(use_mock: bool = False) -> EvalReport:
    results: list[ExtractorResult] = []

    for fixture_name in EVAL_FIXTURES:
        file_path = _find_fixture_file(fixture_name)
        if file_path is None:
            results.append(
                ExtractorResult(
                    fixture=fixture_name,
                    success=False,
                    error="no_fixture_file",
                )
            )
            continue

        if use_mock:
            results.append(
                ExtractorResult(
                    fixture=fixture_name,
                    success=True,
                    extracted={
                        "title": f"Mock Title for {fixture_name}",
                        "document_type": "law",
                    },
                    latency_ms=5.0,
                )
            )
            continue

        try:
            from docling.document_extractor import DocumentExtractor

            extractor = DocumentExtractor()
            start = time.perf_counter()
            extraction_result = extractor.extract(
                source=file_path,
                template=LegalDocumentSchema,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            extracted_data = {}
            if hasattr(extraction_result, "document") and extraction_result.document:
                doc = extraction_result.document
                if hasattr(doc, "model_dump"):
                    extracted_data = doc.model_dump()
                elif isinstance(doc, dict):
                    extracted_data = doc
                else:
                    extracted_data = {"raw": str(doc)}
            elif hasattr(extraction_result, "dict"):
                extracted_data = extraction_result.dict()
            else:
                extracted_data = {"raw": str(extraction_result)}

            results.append(
                ExtractorResult(
                    fixture=fixture_name,
                    success=True,
                    extracted=extracted_data,
                    latency_ms=elapsed_ms,
                )
            )
        except Exception as e:
            results.append(
                ExtractorResult(
                    fixture=fixture_name,
                    success=False,
                    error=f"{type(e).__name__}: {e}",
                )
            )

    return EvalReport(results=results)


def main():
    parser = argparse.ArgumentParser(description="Docling DocumentExtractor evaluation spike")
    parser.add_argument("--mock", action="store_true", help="Use mock extraction (CI-safe)")
    args = parser.parse_args()

    report = run_eval(use_mock=args.mock)

    print(f"\n{'=' * 60}")
    print(f"Docling DocumentExtractor Evaluation {'(mock)' if args.mock else '(live)'}")
    print(f"{'=' * 60}")
    print(f"Total fixtures: {report.total}")
    print(f"Successful: {report.successful}/{report.total}")
    print(f"Avg latency: {report.avg_latency_ms:.0f}ms")
    print()

    for r in report.results:
        status = "OK" if r.success else "FAIL"
        print(f"  [{status}] {r.fixture} ({r.latency_ms:.0f}ms)")
        if r.success and r.extracted:
            for k, v in r.extracted.items():
                if v is not None:
                    print(f"       {k}: {v}")
        if r.error:
            print(f"       error: {r.error}")

    return 0 if report.successful == report.total else 1


if __name__ == "__main__":
    sys.exit(main())
