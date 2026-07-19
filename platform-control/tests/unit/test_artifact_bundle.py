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

    Before #628 the provider established the window and the manifest dropped it,
    so every federal norm answered `in_force_state: unknown` downstream even
    though acquisition knew the answer.
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


def test_build_bundle_extraction_hints_omits_unknown_in_force_window() -> None:
    """An unknown window is omitted, never defaulted — in-force logic must be
    free to answer `unknown` rather than be handed a guess."""
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
