from __future__ import annotations

from platform_control.events.artifact_bundle import build_artifact_bundle_manifest


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
