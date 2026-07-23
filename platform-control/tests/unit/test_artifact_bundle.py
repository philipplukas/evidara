from __future__ import annotations

from platform_control.events.artifact_bundle import (
    build_artifact_bundle_manifest,
    build_bundle_extraction_hints,
)


def test_build_manifest_skips_invalid_content_type_entries() -> None:
    manifest = build_artifact_bundle_manifest(
        bundle_manifest_id="abm_01jq7ab8x4nm7m3qz3b8e9q2fk",
        source_snapshot_id="snap_01jq7a7n3nbzj6sk7v95p9frz1",
        source_id="src_01jq79xv3wdd6yr8q5bn0m3zfk",
        source_version_id="sv_01jq79zcskf4m3m4gm3t5s59xq",
        run_id="run_01jq7a3s9b7j4dndd9sgv6pb9d",
        jurisdiction_id="jur_ch_federal",
        authority_id="auth_fedlex",
        authority_name="Fedlex",
        upstream_locator="https://example.com/decision/1",
        artifacts=[
            {"artifact_id": "art_1", "artifact_role": "primary_document", "storage_ref": {}},
            {
                "artifact_id": "art_2",
                "artifact_role": "attachment",
                "storage_ref": {"content_type": "text/html"},
            },
            {"artifact_id": "art_3", "artifact_role": "metadata"},
        ],
    )

    assert manifest["parser_hints"]["expected_content_types"] == ["text/html"]
    assert manifest["source_defaults"]["authority_name"] == "Fedlex"


def test_build_bundle_extraction_hints_prefers_page_title_metadata() -> None:
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "metadata": {
                "title": "Decision 1",
            },
        },
        document_type_hint="decision",
        authority_display_hint="Zurich Administrative Court",
    )

    assert hints == {
        "title_hint": "Decision 1",
        "document_type_hint": "decision",
        "authority_display_hint": "Zurich Administrative Court",
    }


def test_build_bundle_extraction_hints_prefers_short_title_and_skips_placeholder_title() -> None:
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "provider_metadata": {
                "provider": "fedlex_sparql",
                "title": "RIS Dokument",
                "short_title": (
                    "Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999"
                ),
            }
        }
    )

    assert hints == {
        "title_hint": "Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999",
    }


def test_build_bundle_extraction_hints_carries_provider_in_force_window() -> None:
    """The in-force window must survive into the manifest DI actually receives.

    Before #628 the provider established the window and the manifest dropped it
    — DI's artifact loader keeps only the body bytes — so every federal norm
    answered `in_force_state: unknown` downstream even though acquisition knew
    the answer.
    """
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "provider_metadata": {
                "provider": "fedlex_sparql",
                "short_title": "Bundesverfassung",
                "in_force_from": "2024-03-03",
                "in_force_until": "2028-12-31",
            }
        }
    )

    assert hints["in_force_from_hint"] == "2024-03-03"
    assert hints["in_force_until_hint"] == "2028-12-31"


def test_build_bundle_extraction_hints_carries_ris_in_force_window() -> None:
    """The same hop, exercised on the Austrian RIS path (#663).

    ``ris_ogd`` reads the window from `BrKons.Inkrafttretensdatum` /
    `Ausserkrafttretensdatum`; the helper is provider-agnostic, and this pins
    that the AT path is carried identically to the CH federal one.
    """
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "provider_metadata": {
                "provider": "ris_ogd",
                "short_title": "Test-Verordnung",
                "in_force_from": "1998-04-24",
                "in_force_until": "2018-12-31",
            }
        }
    )

    assert hints["in_force_from_hint"] == "1998-04-24"
    assert hints["in_force_until_hint"] == "2018-12-31"


def test_build_bundle_extraction_hints_omits_unknown_in_force_window() -> None:
    """An unknown window is omitted, never defaulted.

    In-force logic is four-valued so it can answer `unknown`; handing it a guess
    defeats the design (ADR-0033).
    """
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "provider_metadata": {
                "provider": "fedlex_sparql",
                "short_title": "Bundesverfassung",
                # Current consolidation: open-ended, so no end date published.
                "in_force_from": "2024-03-03",
                "in_force_until": None,
            }
        }
    )

    assert hints["in_force_from_hint"] == "2024-03-03"
    assert "in_force_until_hint" not in hints


def test_build_bundle_extraction_hints_omits_unknown_ris_end_date() -> None:
    """Still-in-force RIS norms publish no `Ausserkrafttretensdatum` (#663)."""
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "provider_metadata": {
                "provider": "ris_ogd",
                "short_title": "Test-Verordnung",
                "in_force_from": "2020-01-01",
                "in_force_until": None,
            }
        }
    )

    assert hints["in_force_from_hint"] == "2020-01-01"
    assert "in_force_until_hint" not in hints


def test_build_bundle_extraction_hints_carries_communal_as_number() -> None:
    """The legislative identifier must survive into the manifest DI receives (#755).

    `554.510` is the official citation of the Zürich Hundegesetz — the number a
    lawyer types to look it up. `gemeinde_http` captures it, and before this it
    died at the manifest boundary exactly as the in-force window did above:
    DI's artifact loader keeps only the body bytes. The body is not a fallback
    either, because the number lives in the running header and page-furniture
    removal strips it. Result: a statute unfindable by its own citation.
    """
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "provider_metadata": {
                "provider": "gemeinde_http",
                "as_number": "554.510",
            }
        }
    )

    assert hints["official_citation_hint"] == "554.510"


def test_build_bundle_extraction_hints_carries_lexfind_systematic_number() -> None:
    """The same hop on the cantonal path — one provider, 26 cantons (#731).

    LexFind names the concept `systematic_number` rather than `as_number`.
    Pinning both here keeps the promotion provider-agnostic, so the cantonal
    rung is addressable by citation without a second code path.
    """
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "provider_metadata": {
                "provider": "lexfind_api",
                "systematic_number": "554.510",
            }
        }
    )

    assert hints["official_citation_hint"] == "554.510"


def test_build_bundle_extraction_hints_omits_absent_legislative_identifier() -> None:
    """Absent stays absent. A court decision has no systematic number, and an
    empty-string citation would be worse than none: it renders as a blank
    citation line the reader reads as authoritative."""
    hints = build_bundle_extraction_hints(
        artifact_metadata={
            "provider_metadata": {
                "provider": "gemeinde_http",
                "as_number": None,
                "short_title": "Ein Entscheid",
            }
        }
    )

    assert "official_citation_hint" not in hints
