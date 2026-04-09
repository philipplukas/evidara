"""Decode Google Cloud Pub/Sub HTTP push delivery envelopes."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any


def decode_pubsub_push_json(body: Any) -> dict[str, Any]:
    """Return the JSON object from a request body (direct event or Pub/Sub push wrapper)."""
    if not isinstance(body, dict):
        msg = "DI webhook body must be a JSON object"
        raise ValueError(msg)
    message = body.get("message")
    if isinstance(message, dict) and "data" in message:
        raw_b64 = message.get("data")
        if not isinstance(raw_b64, str):
            msg = "pubsub message.data must be a base64 string"
            raise ValueError(msg)
        try:
            decoded = base64.b64decode(raw_b64, validate=True)
        except binascii.Error as error:
            msg = "pubsub message.data is not valid base64"
            raise ValueError(msg) from error
        inner = json.loads(decoded.decode("utf-8"))
        if not isinstance(inner, dict):
            msg = "pubsub message payload must be a JSON object"
            raise ValueError(msg)
        return inner
    return body
