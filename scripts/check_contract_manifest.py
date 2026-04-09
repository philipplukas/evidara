#!/usr/bin/env python3
"""Validate the versioned MVP contract manifest."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import yaml


MANIFEST_PATH = Path("contracts/manifest.yaml")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
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


def load_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_semver(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not SEMVER_PATTERN.match(value):
        raise ValueError(f"{field_name} must be a semver string (for example 1.2.3).")
    return value


def extract_schema_const(schema: object, property_name: str) -> object | None:
    if not isinstance(schema, dict):
        return None

    properties = schema.get("properties")
    if isinstance(properties, dict):
        property_schema = properties.get(property_name)
        if isinstance(property_schema, dict) and "const" in property_schema:
            return property_schema["const"]

    for branch in schema.get("allOf", []):
        const_value = extract_schema_const(branch, property_name)
        if const_value is not None:
            return const_value

    return None


def event_versions_match(manifest_version: str, schema_version: object) -> bool:
    if isinstance(schema_version, int):
        return manifest_version == f"{schema_version}.0.0"
    if isinstance(schema_version, str):
        return manifest_version == schema_version
    return False


def main() -> int:
    if not MANIFEST_PATH.exists():
        return fail(f"Missing contract manifest: {MANIFEST_PATH}")

    data = load_yaml(MANIFEST_PATH)
    if not isinstance(data, dict):
        return fail("contracts/manifest.yaml must be a mapping object.")

    missing = [k for k in REQUIRED_TOP_LEVEL if k not in data]
    if missing:
        return fail(f"Missing top-level manifest keys: {', '.join(missing)}")

    try:
        ensure_semver(data.get("version"), "version")
    except ValueError as exc:
        return fail(str(exc))

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
        contract_path = Path(path_value)
        if not contract_path.exists():
            return fail(f"apis.{service}.file does not exist: {path_value}")
        try:
            version_value = ensure_semver(api_entry.get("version"), f"apis.{service}.version")
        except ValueError as exc:
            return fail(str(exc))

        contract_data = load_yaml(contract_path)
        if not isinstance(contract_data, dict):
            return fail(f"apis.{service}.file must contain a mapping object: {path_value}")
        contract_version = (
            contract_data.get("info", {}).get("version")
            if isinstance(contract_data.get("info"), dict)
            else None
        )
        if contract_version != version_value:
            return fail(
                f"apis.{service}.version ({version_value}) does not match "
                f"{path_value} info.version ({contract_version})."
            )

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
        producer = event.get("producer")
        consumers = event.get("consumers")
        if not isinstance(name, str) or not name:
            return fail(f"events[{idx}].name must be a non-empty string.")
        if not isinstance(schema, str) or not schema:
            return fail(f"events[{idx}].schema must be a non-empty string.")
        try:
            event_version = ensure_semver(event_version, f"events[{idx}].event_version")
        except ValueError as exc:
            return fail(str(exc))
        if not isinstance(producer, str) or not producer:
            return fail(f"events[{idx}].producer must be a non-empty string.")
        if not isinstance(consumers, list) or not consumers:
            return fail(f"events[{idx}].consumers must be a non-empty list.")
        if any(not isinstance(consumer, str) or not consumer for consumer in consumers):
            return fail(f"events[{idx}].consumers entries must be non-empty strings.")

        schema_path = Path(schema)
        if not schema_path.exists():
            return fail(f"events[{idx}].schema does not exist: {schema}")

        schema_data = load_json(schema_path)
        schema_event_type = extract_schema_const(schema_data, "event_type")
        if schema_event_type != name:
            return fail(
                f"events[{idx}].name ({name}) does not match {schema} event_type const "
                f"({schema_event_type})."
            )
        schema_event_version = extract_schema_const(schema_data, "event_version")
        if not event_versions_match(event_version, schema_event_version):
            return fail(
                f"events[{idx}].event_version ({event_version}) does not match {schema} "
                f"event_version const ({schema_event_version})."
            )
        schema_producer = extract_schema_const(schema_data, "producer")
        if schema_producer != producer:
            return fail(
                f"events[{idx}].producer ({producer}) does not match {schema} producer const "
                f"({schema_producer})."
            )
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
