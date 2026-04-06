#!/usr/bin/env python3
"""Validate the versioned MVP contract manifest."""

from __future__ import annotations

from pathlib import Path
import sys
import yaml


MANIFEST_PATH = Path("contracts/manifest.yaml")
REQUIRED_TOP_LEVEL = (
    "version",
    "last_reviewed",
    "owner",
    "mvp_flow",
    "apis",
    "events",
    "compatibility_policy",
)
REQUIRED_EVENTS = {
    "artifact_bundle.available",
    "document.processing_status.updated",
    "document.processed",
}


def fail(message: str) -> int:
    print(f"❌ {message}", file=sys.stderr)
    return 1


def main() -> int:
    if not MANIFEST_PATH.exists():
        return fail(f"Missing contract manifest: {MANIFEST_PATH}")

    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return fail("contracts/manifest.yaml must be a mapping object.")

    missing = [k for k in REQUIRED_TOP_LEVEL if k not in data]
    if missing:
        return fail(f"Missing top-level manifest keys: {', '.join(missing)}")

    apis = data.get("apis", {})
    if not isinstance(apis, dict):
        return fail("apis must be a mapping.")
    for service in ("platform_control", "document_intelligence", "legal_search"):
        if service not in apis:
            return fail(f"Missing apis.{service} contract declaration.")
        api_entry = apis[service]
        if not isinstance(api_entry, dict):
            return fail(f"apis.{service} must be a mapping.")
        path_value = api_entry.get("file")
        if not path_value or not isinstance(path_value, str):
            return fail(f"apis.{service}.file must be a non-empty string.")
        if not Path(path_value).exists():
            return fail(f"apis.{service}.file does not exist: {path_value}")
        version_value = api_entry.get("version")
        if not version_value or not isinstance(version_value, str):
            return fail(f"apis.{service}.version must be a non-empty string.")

    events = data.get("events", [])
    if not isinstance(events, list):
        return fail("events must be a list.")

    declared_event_names = set()
    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            return fail(f"events[{idx}] must be a mapping.")
        name = event.get("name")
        schema = event.get("schema")
        event_version = event.get("event_version")
        if not isinstance(name, str) or not name:
            return fail(f"events[{idx}].name must be a non-empty string.")
        if not isinstance(schema, str) or not schema:
            return fail(f"events[{idx}].schema must be a non-empty string.")
        if not isinstance(event_version, str) or not event_version:
            return fail(f"events[{idx}].event_version must be a non-empty string.")
        if not Path(schema).exists():
            return fail(f"events[{idx}].schema does not exist: {schema}")
        declared_event_names.add(name)

    missing_required_events = sorted(REQUIRED_EVENTS - declared_event_names)
    if missing_required_events:
        return fail(
            "Manifest is missing required MVP events: "
            + ", ".join(missing_required_events)
        )

    flow = data.get("mvp_flow", {})
    if not isinstance(flow, dict) or not isinstance(flow.get("sequence"), list):
        return fail("mvp_flow.sequence must be a list.")
    if len(flow["sequence"]) < 5:
        return fail("mvp_flow.sequence must include the full ingest-to-search path.")

    print("✅ Contract manifest validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
