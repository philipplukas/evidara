"""Metadata precision/recall-style report over golden fixtures (jurisdiction-aware).

Reads ``metadata_eval`` from each fixture's ``expected.json`` when present::

    "metadata_eval": {
      "expect": {
        "title_contains": "substring",
        "document_type": "decision",
        "source_family": "decision",
        "llm_invoked": false
      }
    }

Run from ``document-intelligence/``::

    uv run python tests/metadata_eval.py
    uv run python tests/metadata_eval.py --fixture ris_xml_decision_vfgh

Exit code 1 if any expectation fails.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.contracts.envelope import ArtifactBundleManifest
from document_intelligence.pipeline import ProcessingPipeline
from test_golden import materialize_golden_fixture


@dataclass
class RowResult:
    fixture: str
    jurisdiction_id: str | None
    passed: bool
    failures: list[str] = field(default_factory=list)


def _load_expect(fixture_name: str) -> dict[str, Any] | None:
    root = os.path.join(os.path.dirname(__file__), "golden", fixture_name, "expected.json")
    if not os.path.isfile(root):
        return None
    data = json.loads(open(root, encoding="utf-8").read())
    return data.get("metadata_eval")


def _check_expect(doc: Any, expect: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    title = doc.title or ""
    if "title_contains" in expect:
        needle = str(expect["title_contains"]).lower()
        if needle not in title.lower():
            failures.append(f"title_contains:{expect['title_contains']!r} not in {title!r}")
    if "document_type" in expect:
        want = expect["document_type"]
        if (doc.document_type or "") != want:
            failures.append(f"document_type: want {want!r} got {doc.document_type!r}")
    if "source_family" in expect:
        want = expect["source_family"]
        fp = doc.metadata.get("field_provenance", {})
        got = (fp.get("source_family") or {}).get("value") or doc.document_type
        if str(got) != str(want):
            failures.append(f"source_family: want {want!r} got {got!r}")
    if "llm_invoked" in expect:
        want = bool(expect["llm_invoked"])
        got = bool((doc.metadata.get("llm_extraction") or {}).get("llm_invoked", False))
        if got != want:
            failures.append(f"llm_invoked: want {want} got {got}")
    return failures


def run_rows(fixture_filter: str | None) -> list[RowResult]:
    golden_root = os.path.join(os.path.dirname(__file__), "golden")
    names = sorted(
        d for d in os.listdir(golden_root) if os.path.isdir(os.path.join(golden_root, d)) and not d.startswith(".")
    )
    if fixture_filter:
        names = [n for n in names if n == fixture_filter]

    rows: list[RowResult] = []
    for name in names:
        me = _load_expect(name)
        if not me or "expect" not in me:
            continue
        expect = me["expect"]
        temp_dir, event_payload, _expected = materialize_golden_fixture(name)
        try:
            result = ProcessingPipeline(processing_version="di_metadata_eval").process_event(event_payload)
            manifest = ArtifactBundleManifest.from_dict(
                json.loads(open(os.path.join(temp_dir, "bundle-manifest.json"), encoding="utf-8").read())
            )
            jid = manifest.source_defaults.get("jurisdiction_id")
            fails = _check_expect(result.document, expect)
            rows.append(
                RowResult(
                    fixture=name,
                    jurisdiction_id=str(jid) if jid else None,
                    passed=not fails,
                    failures=fails,
                )
            )
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Metadata eval over golden fixtures")
    ap.add_argument("--fixture", type=str, default=None, help="Single fixture name")
    args = ap.parse_args()

    rows = run_rows(args.fixture)
    if not rows:
        print("No fixtures with metadata_eval.expect in expected.json (use --fixture or add metadata_eval).")
        return 0

    by_jur: dict[str | None, list[RowResult]] = defaultdict(list)
    for r in rows:
        by_jur[r.jurisdiction_id].append(r)

    print("metadata_eval report")
    print("=" * 72)
    ok = sum(1 for r in rows if r.passed)
    print(f"fixtures evaluated: {len(rows)}  passed: {ok}  failed: {len(rows) - ok}")
    print()
    for r in rows:
        st = "PASS" if r.passed else "FAIL"
        print(f"  [{st}] {r.fixture}  jurisdiction={r.jurisdiction_id!r}")
        for f in r.failures:
            print(f"        - {f}")
    print()
    print("By jurisdiction_id:")
    for jur, group in sorted(by_jur.items(), key=lambda x: (x[0] is None, str(x[0]))):
        gok = sum(1 for r in group if r.passed)
        print(f"  {jur!r}: {gok}/{len(group)} passed")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
