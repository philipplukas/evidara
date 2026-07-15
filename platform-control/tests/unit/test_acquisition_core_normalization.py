from __future__ import annotations

from base64 import b64decode
from hashlib import sha256

import pytest

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
    # Text manifestations keep the verbatim inline body and are hashed as UTF-8 (#590).
    assert raw_artifact.metadata["inline_body_encoding"] == "utf-8"
    assert "inline_body_base64" not in raw_artifact.metadata


# --- Binary manifestations (#590) --------------------------------------------------
# Municipal Swiss law is largely PDF-only, so a provider must be able to carry raw
# bytes end-to-end. These tests pin the contract for the binary path.

# A minimal but valid PDF byte payload (header + EOF). Not decode-able as text.
_PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n\xff\xfe\x00binary"


def test_provider_resource_requires_exactly_one_manifestation() -> None:
    with pytest.raises(ValueError):
        ProviderResource(
            source_url="https://example.com/x",
            final_url="https://example.com/x",
            content_type="application/pdf",
        )
    with pytest.raises(ValueError):
        ProviderResource(
            source_url="https://example.com/x",
            final_url="https://example.com/x",
            content_type="application/pdf",
            body="text",
            body_bytes=b"bytes",
        )


def test_provider_resource_binary_helpers() -> None:
    text_resource = ProviderResource(
        source_url="https://example.com/x",
        final_url="https://example.com/x",
        content_type="text/html",
        body="<p>hi</p>",
    )
    assert text_resource.is_binary is False
    assert text_resource.raw_bytes == b"<p>hi</p>"

    pdf_resource = ProviderResource(
        source_url="https://example.com/x.pdf",
        final_url="https://example.com/x.pdf",
        content_type="application/pdf",
        body_bytes=_PDF_BYTES,
    )
    assert pdf_resource.is_binary is True
    assert pdf_resource.raw_bytes == _PDF_BYTES


def test_artifact_pipeline_carries_binary_pdf_without_corruption() -> None:
    pipeline = ArtifactPipeline()
    resources = [
        ProviderResource(
            source_url="https://stadt-zuerich.ch/554/510.pdf",
            final_url="https://stadt-zuerich.ch/554/510.pdf",
            content_type="application/pdf",
            body_bytes=_PDF_BYTES,
            title="Vollzugsvorschriften zum Hundegesetz",
            http_status=200,
            discovery_depth=1,
        )
    ]

    normalized = pipeline.normalize(run_id="run_pdf", resources=resources)

    assert len(normalized) == 1
    raw_artifact, captured_resource = normalized[0]
    assert raw_artifact.content_type == "application/pdf"
    # Binary bytes survive round-trip byte-for-byte via base64 — never decoded as text.
    assert raw_artifact.metadata["inline_body_encoding"] == "base64"
    assert "inline_body" not in raw_artifact.metadata
    assert b64decode(raw_artifact.metadata["inline_body_base64"]) == _PDF_BYTES
    # Checksum is computed over the raw bytes, not a lossy text decode.
    assert captured_resource.checksum == sha256(_PDF_BYTES).hexdigest()
