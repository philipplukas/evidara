"""Tests for RIS absatz[@ct] metadata extraction and deterministic source family."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.normalize.xml import _resolve_ris_source_family, normalize_xml_document
from support import fixture_path


def _read_fixture_xml(fixture_name: str) -> str:
    fixture_dir = fixture_path("golden", fixture_name)
    for candidate in ("document.xml",):
        path = os.path.join(fixture_dir, candidate)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(f"No XML artifact in {fixture_dir}")


class TestRisCtExtraction:
    def test_consolidated_law_extracts_ct_fields(self):
        xml_text = _read_fixture_xml("ris_xml_law_consolidated")
        ir = normalize_xml_document(xml_text, "test_artifact")
        em = ir.metadata.get("extracted_metadata", {})
        assert em.get("title_short") or em.get("title_long"), f"Expected ct title fields, got: {em.keys()}"

    def test_decision_vfgh_extracts_court(self):
        xml_text = _read_fixture_xml("ris_xml_decision_vfgh")
        ir = normalize_xml_document(xml_text, "test_artifact")
        em = ir.metadata.get("extracted_metadata", {})
        assert "court_name" in em or "geschaeftszahl" in em or "ecli" in em, (
            f"Expected court/gz/ecli from ct= attributes, got: {em.keys()}"
        )

    def test_decision_vwgh_extracts_court(self):
        xml_text = _read_fixture_xml("ris_xml_decision_vwgh")
        ir = normalize_xml_document(xml_text, "test_artifact")
        em = ir.metadata.get("extracted_metadata", {})
        assert "court_name" in em or "geschaeftszahl" in em or "ecli" in em, (
            f"Expected court/gz/ecli from ct= attributes, got: {em.keys()}"
        )

    def test_law_short_has_title(self):
        xml_text = _read_fixture_xml("ris_xml_law_short")
        ir = normalize_xml_document(xml_text, "test_artifact")
        assert ir.metadata.get("title"), "Expected a title from ris_xml_law_short"
        assert "Notarstelle" in (ir.metadata.get("title") or ""), "Title should mention Notarstelle"


class TestRisSourceFamily:
    def test_decision_from_court_name(self):
        assert _resolve_ris_source_family({"court_name": "Verfassungsgerichtshof"}) == "decision"

    def test_decision_from_ecli(self):
        assert _resolve_ris_source_family({"ecli": "ECLI:AT:VFGH:2025:V258.2025"}) == "decision"

    def test_decision_from_geschaeftszahl(self):
        assert _resolve_ris_source_family({"geschaeftszahl": "V258/2025"}) == "decision"

    def test_decision_from_type_code(self):
        assert _resolve_ris_source_family({"document_type": "E"}) == "decision"
        assert _resolve_ris_source_family({"document_type": "RS"}) == "decision"

    def test_law_from_type_code(self):
        assert _resolve_ris_source_family({"document_type": "BG"}) == "law"
        assert _resolve_ris_source_family({"document_type": "V"}) == "law"

    def test_law_from_bgbl(self):
        assert _resolve_ris_source_family({"kundmachungsorgan": "BGBl. II Nr. 74/2026"}) == "law"

    def test_law_from_gesetzesnummer(self):
        assert _resolve_ris_source_family({"gesetzesnummer": "10003790"}) == "law"

    def test_unknown_for_empty(self):
        assert _resolve_ris_source_family({}) is None

    def test_vfgh_fixture_classified_as_decision(self):
        xml_text = _read_fixture_xml("ris_xml_decision_vfgh")
        ir = normalize_xml_document(xml_text, "test_artifact")
        assert ir.metadata.get("source_family") == "decision"

    def test_vwgh_fixture_classified_as_decision(self):
        xml_text = _read_fixture_xml("ris_xml_decision_vwgh")
        ir = normalize_xml_document(xml_text, "test_artifact")
        assert ir.metadata.get("source_family") == "decision"

    def test_law_consolidated_classified_as_law(self):
        xml_text = _read_fixture_xml("ris_xml_law_consolidated")
        ir = normalize_xml_document(xml_text, "test_artifact")
        assert ir.metadata.get("source_family") == "law"

    def test_law_short_classified_as_law(self):
        xml_text = _read_fixture_xml("ris_xml_law_short")
        ir = normalize_xml_document(xml_text, "test_artifact")
        family = ir.metadata.get("source_family")
        assert family == "law", f"Expected 'law' but got '{family}'"

    def test_synthetic_ris_classified_as_law(self):
        xml_text = _read_fixture_xml("ris_xml")
        ir = normalize_xml_document(xml_text, "test_artifact")
        assert ir.metadata.get("source_family") == "law"
