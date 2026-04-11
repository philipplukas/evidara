"""Tests for canonical jurisdiction ID resolution."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from document_intelligence.canonical.jurisdiction import (
    resolve_jurisdiction_from_manifest,
    resolve_jurisdiction_id,
)


class TestResolveJurisdictionId:
    def test_canonical_id_passthrough(self):
        assert resolve_jurisdiction_id("jur_ch") == "jur_ch"
        assert resolve_jurisdiction_id("jur_ch_federal") == "jur_ch_federal"
        assert resolve_jurisdiction_id("jur_at") == "jur_at"
        assert resolve_jurisdiction_id("jur_at_federal") == "jur_at_federal"

    def test_iso_alpha2_uppercase(self):
        assert resolve_jurisdiction_id("CH") == "jur_ch"
        assert resolve_jurisdiction_id("AT") == "jur_at"
        assert resolve_jurisdiction_id("DE") == "jur_de"
        assert resolve_jurisdiction_id("LI") == "jur_li"

    def test_iso_alpha2_lowercase(self):
        assert resolve_jurisdiction_id("ch") == "jur_ch"
        assert resolve_jurisdiction_id("at") == "jur_at"
        assert resolve_jurisdiction_id("de") == "jur_de"
        assert resolve_jurisdiction_id("li") == "jur_li"

    def test_slug_with_federal(self):
        assert resolve_jurisdiction_id("ch-federal") == "jur_ch_federal"
        assert resolve_jurisdiction_id("at-federal") == "jur_at_federal"

    def test_common_name_aliases(self):
        assert resolve_jurisdiction_id("Switzerland") == "jur_ch"
        assert resolve_jurisdiction_id("Schweiz") == "jur_ch"
        assert resolve_jurisdiction_id("Suisse") == "jur_ch"
        assert resolve_jurisdiction_id("Austria") == "jur_at"
        assert resolve_jurisdiction_id("Österreich") == "jur_at"
        assert resolve_jurisdiction_id("oesterreich") == "jur_at"
        assert resolve_jurisdiction_id("Germany") == "jur_de"
        assert resolve_jurisdiction_id("Deutschland") == "jur_de"
        assert resolve_jurisdiction_id("Liechtenstein") == "jur_li"

    def test_whitespace_is_stripped(self):
        assert resolve_jurisdiction_id("  CH  ") == "jur_ch"
        assert resolve_jurisdiction_id("  jur_ch_federal  ") == "jur_ch_federal"

    def test_none_returns_none(self):
        assert resolve_jurisdiction_id(None) is None

    def test_empty_string_returns_none(self):
        assert resolve_jurisdiction_id("") is None
        assert resolve_jurisdiction_id("   ") is None

    def test_unknown_hint_returns_none(self):
        assert resolve_jurisdiction_id("unknown_country") is None
        assert resolve_jurisdiction_id("XY") is None

    def test_unknown_jur_prefix_passes_through(self):
        # Forward-compatibility: unknown jur_* IDs pass through
        assert resolve_jurisdiction_id("jur_de") == "jur_de"
        assert resolve_jurisdiction_id("jur_li") == "jur_li"
        assert resolve_jurisdiction_id("jur_future_jurisdiction") == "jur_future_jurisdiction"


class TestResolveJurisdictionFromManifest:
    def test_canonical_jurisdiction_id_in_source_defaults(self):
        result = resolve_jurisdiction_from_manifest(
            {"jurisdiction_id": "jur_ch_federal"},
            {},
        )
        assert result == "jur_ch_federal"

    def test_iso_code_in_source_defaults(self):
        result = resolve_jurisdiction_from_manifest(
            {"jurisdiction_id": "CH"},
            {},
        )
        assert result == "jur_ch"

    def test_jurisdiction_hint_field_in_source_defaults(self):
        result = resolve_jurisdiction_from_manifest(
            {"jurisdiction_hint": "at"},
            {},
        )
        assert result == "jur_at"

    def test_jurisdiction_id_takes_priority_over_hint(self):
        result = resolve_jurisdiction_from_manifest(
            {"jurisdiction_id": "jur_ch", "jurisdiction_hint": "jur_at"},
            {},
        )
        assert result == "jur_ch"

    def test_falls_back_to_reference_context_hint(self):
        result = resolve_jurisdiction_from_manifest(
            {},
            {"jurisdiction_hint": "CH"},
        )
        assert result == "jur_ch"

    def test_reference_context_jurisdiction_id_fallback(self):
        result = resolve_jurisdiction_from_manifest(
            {},
            {"jurisdiction_id": "jur_at"},
        )
        assert result == "jur_at"

    def test_none_when_no_hints(self):
        assert resolve_jurisdiction_from_manifest({}, {}) is None
        assert resolve_jurisdiction_from_manifest({}) is None

    def test_none_when_hint_unresolvable(self):
        result = resolve_jurisdiction_from_manifest({"jurisdiction_id": "UNKNOWN"})
        assert result is None

    def test_reference_context_none_is_safe(self):
        result = resolve_jurisdiction_from_manifest({"jurisdiction_id": "jur_ch"}, None)
        assert result == "jur_ch"
