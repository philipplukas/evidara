"""Databricks-oriented entrypoint for bundle processing."""

import argparse
import json
from typing import Any

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.ingest.loaders import DispatchingBundleLoader
from document_intelligence.processing_runtime import process_artifact_bundle_event


def run(
    *,
    event_path: str,
    processing_version: str = "",
    surfaces_root_uri: str = "",
    published_documents_uri: str = "",
    published_sections_uri: str = "",
    processing_manifests_uri: str = "",
    parser_backend: str = "",
    enable_spacy: bool = False,
    spacy_model_name: str = "",
    spacy_max_chars_per_section: int = 100000,
    spacy_batch_size: int = 32,
) -> dict[str, Any]:
    runtime_settings = RuntimeSettings.from_mapping(
        {},
        processing_version=processing_version or None,
        surfaces_root_uri=surfaces_root_uri or None,
        published_documents_uri=published_documents_uri or None,
        published_sections_uri=published_sections_uri or None,
        processing_manifests_uri=processing_manifests_uri or None,
        parser_backend=parser_backend or None,
        enable_spacy=enable_spacy,
        spacy_model_name=spacy_model_name or None,
        spacy_max_chars_per_section=spacy_max_chars_per_section,
        spacy_batch_size=spacy_batch_size,
    )
    if runtime_settings.surface_uris is None:
        raise ValueError(
            "Databricks runtime requires DI_SURFACES_ROOT_URI or all three explicit published surface URIs"
        )

    with open(event_path, encoding="utf-8") as event_file:
        event_payload = json.load(event_file)

    output = process_artifact_bundle_event(
        event_payload,
        runtime_settings=runtime_settings,
        bundle_loader=DispatchingBundleLoader(),
        require_surface_uris=True,
    )

    return {
        "document_id": output["document_id"],
        "document_revision": output["document_revision"],
        "processing_manifest_id": output["processing_manifest_id"],
        "sections": output["sections"],
        "published_documents_uri": runtime_settings.surface_uris.published_documents_uri,
        "published_sections_uri": runtime_settings.surface_uris.published_sections_uri,
        "processing_manifests_uri": runtime_settings.surface_uris.processing_manifests_uri,
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="document_intelligence_databricks_process_event",
        description="Process a bundle event using Delta-backed published surfaces.",
    )
    parser.add_argument("--event-path", required=True)
    parser.add_argument("--processing-version", default="")
    parser.add_argument("--surfaces-root-uri", default="")
    parser.add_argument("--published-documents-uri", default="")
    parser.add_argument("--published-sections-uri", default="")
    parser.add_argument("--processing-manifests-uri", default="")
    parser.add_argument("--parser-backend", default="")
    parser.add_argument(
        "--enable-spacy",
        action="store_true",
        help="Enable optional spaCy enrichment metadata.",
    )
    parser.add_argument("--spacy-model-name", default="")
    parser.add_argument("--spacy-max-chars-per-section", type=int, default=100000)
    parser.add_argument("--spacy-batch-size", type=int, default=32)
    args = parser.parse_args(argv)

    output = run(
        event_path=args.event_path,
        processing_version=args.processing_version,
        surfaces_root_uri=args.surfaces_root_uri,
        published_documents_uri=args.published_documents_uri,
        published_sections_uri=args.published_sections_uri,
        processing_manifests_uri=args.processing_manifests_uri,
        parser_backend=args.parser_backend,
        enable_spacy=args.enable_spacy,
        spacy_model_name=args.spacy_model_name,
        spacy_max_chars_per_section=args.spacy_max_chars_per_section,
        spacy_batch_size=args.spacy_batch_size,
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
