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
    with open(event_path, encoding="utf-8") as event_file:
        event_payload = json.load(event_file)

    runtime_settings = RuntimeSettings.from_environment()
    output = process_artifact_bundle_event(
        event_payload,
        runtime_settings=runtime_settings,
    )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
