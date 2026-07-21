"""The title predicate that keeps a filename out of a title slot (#771).

Fedlex serves some consolidated acts as HTML generated from a .docx and leaves the
source filename in `<title>`. Taken as a title, it made the Tierschutzgesetz
unfindable by its own name while its text sat correctly in the index.
"""

from __future__ import annotations

import pytest

from document_intelligence.normalize.titles import is_placeholder_title, looks_like_filename

# The exact string observed in the index on 2026-07-21, and the `<title>` Fedlex
# actually serves for /eli/cc/2008/414.
TSCHG_LEAKED_FILENAME = "fedlex-data-admin-ch-eli-cc-2008-414-20230901-de-docx"


@pytest.mark.parametrize(
    "title",
    [
        TSCHG_LEAKED_FILENAME,
        "fedlex-data-admin-ch-eli-cc-2008-416-20230901-de-html",
        "some-export-2024-final.pdf",
        "ris_bundesrecht_2019_01_01.xml",
    ],
)
def test_a_leaked_filename_is_not_a_title(title: str) -> None:
    assert looks_like_filename(title) is True
    assert is_placeholder_title(title) is True


@pytest.mark.parametrize(
    "title",
    [
        # Single-word statute names are real titles and must survive — this is the
        # case a bare "no whitespace" rule would have destroyed.
        "Tierschutzgesetz",
        "Bundesverfassung",
        "Tierschutzgesetz vom 16. Dezember 2005 (TSchG)",
        "Vollzugsvorschriften zum Hundegesetz",
        # Hyphenated real titles, including one ending in a word that is not a
        # format token.
        "Verordnung-Nr-5",
        "E-Government-Gesetz",
        # A title that merely contains a dot.
        "Art. 80 BV",
    ],
)
def test_a_real_title_is_kept(title: str) -> None:
    assert looks_like_filename(title) is False
    assert is_placeholder_title(title) is False


def test_the_curated_placeholders_still_hold() -> None:
    # TSchV's `<title>` is literally "Fedlex"; that is why it was titled correctly
    # while TSchG was not. Losing this would regress the sibling case.
    assert is_placeholder_title("Fedlex") is True
    assert is_placeholder_title("RIS Dokument") is True
    assert is_placeholder_title("RIS — Dokument") is True
    assert is_placeholder_title("Untitled document") is True
    assert is_placeholder_title("   ") is True
    assert is_placeholder_title(None) is True


def test_a_format_token_alone_is_not_enough() -> None:
    # Only two separators or more. Keeps the rule off short real titles that happen
    # to end in a format-like word.
    assert looks_like_filename("Anhang-pdf") is False
    assert looks_like_filename("plan.txt") is False


def _ir(structured: str | None, hint: str | None, heading: str | None = None):
    from document_intelligence.normalize.ir import Block, NormalizedDocumentIR

    metadata: dict = {}
    if structured is not None:
        metadata["title"] = structured
    if hint is not None:
        metadata["extraction_hints"] = {"title_hint": hint}
    blocks = []
    if heading is not None:
        blocks.append(Block(id="b1", type="heading", text=heading, order=0, artifact_id="art_1"))
    return NormalizedDocumentIR(blocks=blocks, metadata=metadata)


def test_the_acquisition_hint_beats_a_leaked_filename() -> None:
    """The #771 path, end to end through the resolver.

    The platform captured `Tierschutzgesetz vom 16. Dezember 2005 (TSchG)` correctly
    and then discarded it, because the leaked filename was not on any placeholder
    list and so ranked as a legitimate structured title.
    """
    from document_intelligence.pipeline import _effective_title_from_normalized

    title, source = _effective_title_from_normalized(
        _ir(structured=TSCHG_LEAKED_FILENAME, hint="Tierschutzgesetz vom 16. Dezember 2005 (TSchG)")
    )

    assert title == "Tierschutzgesetz vom 16. Dezember 2005 (TSchG)"
    assert source == "manifest"


def test_a_real_structured_title_still_wins_over_a_hint() -> None:
    # The fix must not invert the normal precedence: a genuine title parsed from the
    # body is still preferred over an acquisition hint.
    from document_intelligence.pipeline import _effective_title_from_normalized

    title, source = _effective_title_from_normalized(
        _ir(structured="Tierschutzverordnung vom 23. April 2008 (TSchV)", hint="TSchV")
    )

    assert title == "Tierschutzverordnung vom 23. April 2008 (TSchV)"
    assert source == "structured"


def test_a_leaked_filename_with_no_hint_falls_back_to_a_heading() -> None:
    # With nothing better available the body heading is used. "Untitled document"
    # would still beat presenting a filename as the name of a law.
    from document_intelligence.pipeline import _effective_title_from_normalized

    title, source = _effective_title_from_normalized(
        _ir(structured=TSCHG_LEAKED_FILENAME, hint=None, heading="Tierschutzgesetz")
    )

    assert title == "Tierschutzgesetz"
    assert source == "structured"
