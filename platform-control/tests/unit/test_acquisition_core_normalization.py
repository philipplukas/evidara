from __future__ import annotations

from acquisition_core.normalization import ArtifactPipeline
from acquisition_core.providers import ProviderResource


def test_artifact_pipeline_normalizes_urls_and_checksums() -> None:
    pipeline = ArtifactPipeline()
    resources = [
        ProviderResource(
            source_url="https://example.com/path/?utm_source=test&x=1",
            final_url="https://example.com/path/?utm_source=test&x=1",
            content_type="text/html",
            body="<html><body>Hello world</body></html>",
            title="Sample",
            http_status=200,
            discovery_depth=1,
        )
    ]

    normalized = pipeline.normalize(
        run_id="run_123",
        resources=resources,
        canonicalization_rules={
            "strip_query_params": ["utm_source"],
            "collapse_trailing_slash": True,
        },
    )

    assert len(normalized) == 1
    raw_artifact, captured_resource = normalized[0]
    assert raw_artifact.storage_path == "inline://run_123/0"
    assert raw_artifact.content_type == "text/html"
    assert "inline_body" in raw_artifact.metadata
    assert captured_resource.final_url == "https://example.com/path?x=1"
    assert captured_resource.checksum
