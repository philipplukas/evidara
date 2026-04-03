"""CLI entrypoint for local event processing."""

import json
import sys

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.processing_runtime import process_artifact_bundle_event


def main(argv=None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) != 1:
        print("usage: python -m document_intelligence.jobs.process_event <event.json>")
        return 1

    event_path = args[0]
    with open(event_path, "r", encoding="utf-8") as event_file:
        event_payload = json.load(event_file)

    runtime_settings = RuntimeSettings.from_environment()
    result = ProcessingPipeline(
        sink=_build_sink_from_runtime_settings(runtime_settings),
        processing_version=runtime_settings.processing_version,
        parser_backend=runtime_settings.parser_backend,
        enable_spacy=runtime_settings.enable_spacy,
        spacy_model_name=runtime_settings.spacy_model_name,
        spacy_max_chars_per_section=runtime_settings.spacy_max_chars_per_section,
        spacy_batch_size=runtime_settings.spacy_batch_size,
    ).process_event(event_payload)
    output = {
        "document_id": result.document.document_id,
        "processing_manifest_id": result.manifest.processing_manifest_id,
        "sections": len(result.sections),
        "status_events": result.status_events,
        "document_processed_event": result.document_processed_event,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _build_sink_from_runtime_settings(runtime_settings: RuntimeSettings):
    if runtime_settings.surface_uris is None:
        return InMemoryCanonicalSink()
    return DeltaCanonicalSink(runtime_settings.surface_uris.to_delta_sink_config())


if __name__ == "__main__":
    raise SystemExit(main())
