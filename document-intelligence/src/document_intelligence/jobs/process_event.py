"""CLI entrypoint for local event processing."""

import json
import os
import sys

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.pipeline import ProcessingPipeline
from document_intelligence.persist.sinks import (
    DeltaCanonicalSink,
    InMemoryCanonicalSink,
)


def main(argv=None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) != 1:
        print("usage: python -m document_intelligence.jobs.process_event <event.json>")
        return 1

    event_path = args[0]
    with open(event_path, "r", encoding="utf-8") as event_file:
        event_payload = json.load(event_file)

    result = ProcessingPipeline(
        sink=_build_sink_from_environment(),
        processing_version=os.environ.get("DI_PROCESSING_VERSION", "0.1.0-dev"),
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

def _build_sink_from_environment():
    runtime_settings = RuntimeSettings.from_environment()
    if runtime_settings.surface_uris is None:
        return InMemoryCanonicalSink()
    return DeltaCanonicalSink(runtime_settings.surface_uris.to_delta_sink_config())


if __name__ == "__main__":
    raise SystemExit(main())
