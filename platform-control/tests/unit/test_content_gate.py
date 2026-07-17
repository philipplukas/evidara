"""Unit tests for the shared legal-text density gate (#631).

WHY THIS TEST EXISTS:
The gate is the acquisition-layer guard against capturing a JavaScript
navigation shell as if it were law — the confident-fabrication failure
ADR-0033 exists to prevent, one layer earlier than the reasoning layer.
It must refuse a chrome/nav payload (captured=0 + reason) and pass a real
statute body, across the German and Italian marker vocabularies the
portal providers cover.
"""

from __future__ import annotations

from acquisition_core.content_gate import (
    DEFAULT_MIN_LEGAL_MARKERS,
    assess_legal_text_density,
)

# A JavaScript SPA navigation shell: script/style heavy, visible chrome text,
# zero legal-text markers — the shape of the zh.ch capture in #631.
_NAV_SHELL = (
    "<html><head><title>Kanton Zürich</title>"
    "<style>.nav{color:red}.footer{color:blue}</style>"
    "<script>window.__APP__={routes:['/home','/politik-staat','/verwaltung']};</script>"
    "</head><body>"
    "<nav>Startseite Politik und Staat Verwaltung Kontakt Suche Login</nav>"
    "<script>document.getElementById('app').render();track();</script>"
    "</body></html>"
)

# A real German-language statute snippet.
_STATUTE_DE = (
    "<html><head><title>LS 131.1</title></head><body>"
    "<h1>Art. 1 Zweck</h1>"
    "<p>Art. 2 Abs. 1: Der Kanton schützt ...</p>"
    "<p>Art. 3 Abs. 2 Ziff. 1: ...</p></body></html>"
)

# A real Italian-language statute snippet.
_STATUTE_IT = (
    "<html><body><p>art. 1 comma 1</p><p>art. 2 comma 2</p><p>art. 3 lett. a)</p></body></html>"
)


def test_navigation_shell_is_refused() -> None:
    result = assess_legal_text_density(_NAV_SHELL)
    assert result.is_legal_text is False
    assert result.marker_count == 0
    assert result.reason is not None
    assert "navigation" in result.reason
    # The script/style bulk dwarfs the visible text.
    assert result.script_to_text_ratio > 1.0


def test_german_statute_passes() -> None:
    result = assess_legal_text_density(_STATUTE_DE)
    assert result.is_legal_text is True
    assert result.marker_count >= DEFAULT_MIN_LEGAL_MARKERS
    assert result.reason is None


def test_italian_statute_passes() -> None:
    result = assess_legal_text_density(_STATUTE_IT)
    assert result.is_legal_text is True
    assert result.marker_count >= DEFAULT_MIN_LEGAL_MARKERS
    assert result.reason is None


def test_markers_are_counted_in_visible_text_only() -> None:
    # Markers hiding inside a <script> block must not rescue a chrome page.
    body = "<html><body><script>var s='Art. 1 Art. 2 Art. 3 Abs. 4';</script></body></html>"
    result = assess_legal_text_density(body)
    assert result.marker_count == 0
    assert result.is_legal_text is False


def test_gate_abstains_on_non_text_content_type() -> None:
    # A binary artifact cannot be assessed as text; the gate abstains rather
    # than guessing (the provider's carriability checks own that case).
    result = assess_legal_text_density("%PDF-1.7 ...", content_type="application/pdf")
    assert result.is_legal_text is True
    assert result.reason is None


def test_as_evidence_is_json_safe_diagnostics() -> None:
    evidence = assess_legal_text_density(_NAV_SHELL).as_evidence()
    assert evidence["legal_marker_count"] == 0
    assert evidence["min_legal_markers"] == DEFAULT_MIN_LEGAL_MARKERS
    assert isinstance(evidence["script_to_text_ratio"], float)
