"""Tests for Pub/Sub HTTP push envelope decoding."""

from __future__ import annotations

import base64
import json

import pytest

from platform_control.web.pubsub_push import decode_pubsub_push_json


def test_decode_passes_through_direct_event_dict() -> None:
    inner = {"event_type": "document.processed", "event_version": 1}
    assert decode_pubsub_push_json(inner) == inner


def test_decode_unwraps_pubsub_envelope() -> None:
    inner = {"event_type": "document.processed", "event_version": 1}
    body = {
        "message": {
            "data": base64.b64encode(json.dumps(inner).encode("utf-8")).decode("ascii"),
            "messageId": "1",
        },
        "subscription": "projects/p/subscriptions/s",
    }
    assert decode_pubsub_push_json(body) == inner


def test_decode_rejects_non_object_body() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        decode_pubsub_push_json([])


def test_decode_rejects_invalid_base64() -> None:
    body = {"message": {"data": "not!!!valid_base64"}}
    with pytest.raises(ValueError, match="base64"):
        decode_pubsub_push_json(body)
