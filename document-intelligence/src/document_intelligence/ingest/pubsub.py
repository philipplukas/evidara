"""Helpers for resolving DI inbound events from raw JSON or Pub/Sub push envelopes."""

import base64
import binascii
import json
from collections.abc import Mapping
from typing import Any

from document_intelligence.contracts.envelope import EnvelopeError


def load_artifact_bundle_event(event_path: str) -> dict[str, Any]:
    """Load an inbound artifact-bundle event from a JSON file."""

    with open(event_path, encoding="utf-8") as event_file:
        event_payload = json.load(event_file)
    return resolve_artifact_bundle_event(event_payload)


def resolve_artifact_bundle_event(event_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve either a direct event or a Pub/Sub push envelope to the raw event."""

    if _looks_like_artifact_bundle_event(event_payload):
        return dict(event_payload)
    if _looks_like_pubsub_push_envelope(event_payload):
        return _decode_pubsub_push_envelope(event_payload)
    raise EnvelopeError("expected artifact_bundle.available event or Pub/Sub push envelope")


def _looks_like_artifact_bundle_event(event_payload: Mapping[str, Any]) -> bool:
    return event_payload.get("event_type") == "artifact_bundle.available" and isinstance(
        event_payload.get("payload"), Mapping
    )


def _looks_like_pubsub_push_envelope(event_payload: Mapping[str, Any]) -> bool:
    return isinstance(event_payload.get("message"), Mapping)


def _decode_pubsub_push_envelope(pubsub_envelope: Mapping[str, Any]) -> dict[str, Any]:
    message = pubsub_envelope.get("message")
    if not isinstance(message, Mapping):
        raise EnvelopeError("Pub/Sub push envelope must contain a message object")

    encoded_data = message.get("data")
    if not isinstance(encoded_data, str) or not encoded_data:
        raise EnvelopeError("Pub/Sub push envelope must include message.data")

    try:
        event_bytes = base64.b64decode(encoded_data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise EnvelopeError("Pub/Sub push envelope message.data was not valid base64") from error

    try:
        decoded_payload = json.loads(event_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise EnvelopeError("Pub/Sub push envelope message.data was not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise EnvelopeError("Pub/Sub push envelope message.data was not valid JSON") from error

    if not isinstance(decoded_payload, Mapping):
        raise EnvelopeError("Pub/Sub push envelope message.data must decode to an object")

    return dict(decoded_payload)
