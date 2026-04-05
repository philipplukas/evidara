from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from acquisition_core.providers import ProviderResource


@dataclass(slots=True)
class RawArtifactRecord:
    storage_path: str
    content_type: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class CapturedResourceRecord:
    source_url: str
    final_url: str
    title: str | None
    content_type: str
    checksum: str
    http_status: int | None
    discovery_depth: int | None
    metadata: dict[str, Any]


class ArtifactPipeline:
    def normalize(
        self,
        *,
        run_id: str,
        resources: list[ProviderResource],
        canonicalization_rules: dict[str, Any] | None = None,
    ) -> list[tuple[RawArtifactRecord, CapturedResourceRecord]]:
        pairs: list[tuple[RawArtifactRecord, CapturedResourceRecord]] = []
        strip_query_params = set((canonicalization_rules or {}).get("strip_query_params") or [])
        collapse_trailing_slash = bool(
            (canonicalization_rules or {}).get("collapse_trailing_slash") or False
        )

        for idx, resource in enumerate(resources):
            normalized_url = canonicalize_url(
                resource.final_url or resource.source_url,
                strip_query_params=strip_query_params,
                collapse_trailing_slash=collapse_trailing_slash,
            )
            payload_hash = sha256(resource.body.encode("utf-8")).hexdigest()
            raw_artifact = RawArtifactRecord(
                storage_path=f"inline://{run_id}/{idx}",
                content_type=resource.content_type,
                metadata={
                    "provider_metadata": resource.metadata,
                    "source_url": resource.source_url,
                    "final_url": resource.final_url,
                    "inline_body": resource.body,
                },
            )
            captured_resource = CapturedResourceRecord(
                source_url=resource.source_url,
                final_url=normalized_url,
                title=resource.title,
                content_type=resource.content_type,
                checksum=payload_hash,
                http_status=resource.http_status,
                discovery_depth=resource.discovery_depth,
                metadata=dict(resource.metadata),
            )
            pairs.append((raw_artifact, captured_resource))
        return pairs


def canonicalize_url(
    url: str,
    *,
    strip_query_params: set[str] | None = None,
    collapse_trailing_slash: bool = False,
) -> str:
    split = urlsplit(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if key not in (strip_query_params or set())
    ]
    path = split.path or "/"
    if collapse_trailing_slash and path != "/":
        path = path.rstrip("/")
    query = urlencode(filtered_query, doseq=True)
    return urlunsplit((split.scheme, split.netloc, path, query, ""))
