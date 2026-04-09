"""Outbound Pub/Sub publishing from process_artifact_bundle_event."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from document_intelligence.canonical.models import ProcessingResult
from document_intelligence.processing_runtime import (
    process_artifact_bundle_event,
    publish_processing_result_to_pubsub,
)
from support import build_bundle_event, build_manifest_payload


class ProcessingRuntimePubSubTests(unittest.TestCase):
    def test_skips_publish_without_project_id(self) -> None:
        result = MagicMock(spec=ProcessingResult)
        result.status_events = [{"event_type": "document.processing_status.updated"}]
        result.document_processed_event = {"event_type": "document.processed"}
        with patch.dict(os.environ, {}, clear=True):
            publish_processing_result_to_pubsub(result, publisher=MagicMock())
        # publisher passed but should not be called when no DI_GCP_PROJECT_ID
        result_mock = MagicMock()
        publish_processing_result_to_pubsub(result, publisher=result_mock)
        result_mock.publish_status_event.assert_not_called()
        result_mock.publish_document_processed_event.assert_not_called()

    def test_skips_publish_when_backend_disabled(self) -> None:
        result = MagicMock(spec=ProcessingResult)
        result.status_events = []
        result.document_processed_event = {}
        mock_pub = MagicMock()
        with patch.dict(
            os.environ,
            {"DI_GCP_PROJECT_ID": "p1", "DI_EVENT_PUBLISHER_BACKEND": "noop"},
            clear=False,
        ):
            publish_processing_result_to_pubsub(result, publisher=mock_pub)
        mock_pub.publish_status_event.assert_not_called()

    def test_process_event_invokes_publish_when_project_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = os.path.join(temp_dir, "document.html")
            manifest_path = os.path.join(temp_dir, "bundle-manifest.json")
            with open(artifact_path, "w", encoding="utf-8") as f:
                f.write("<html><head><title>T</title></head><body><h1>A</h1><p>B</p></body></html>")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(
                    build_manifest_payload(
                        artifact_path,
                        artifact_role="primary_document",
                    ),
                    f,
                )
            payload = build_bundle_event(manifest_path)
            surfaces = os.path.join(temp_dir, "delta_surfaces")
            env = {
                "DI_SURFACES_ROOT_URI": surfaces,
                "DI_GCP_PROJECT_ID": "test-project",
                "DI_STATUS_TOPIC_NAME": "status-topic",
                "DI_PROCESSED_TOPIC_NAME": "processed-topic",
            }
            calls: list[tuple[str, dict]] = []

            class FakePublisher:
                def publish_status_event(self, event: dict) -> None:
                    calls.append(("status", event))

                def publish_document_processed_event(self, event: dict) -> None:
                    calls.append(("processed", event))

            with patch.dict(os.environ, env, clear=False):
                with patch(
                    "document_intelligence.processing_runtime.PubSubEventPublisher",
                    return_value=FakePublisher(),
                ) as ctor:
                    out = process_artifact_bundle_event(payload)
                    ctor.assert_called_once()
                    cfg = ctor.call_args[0][0]
                    self.assertEqual(cfg.project_id, "test-project")
                    self.assertEqual(cfg.status_topic_name, "status-topic")
                    self.assertEqual(cfg.processed_topic_name, "processed-topic")

            self.assertEqual(out["status"], "processed")
            self.assertEqual(len(calls), 4)
            self.assertEqual(calls[0][0], "status")
            self.assertEqual(calls[1][0], "status")
            self.assertEqual(calls[2][0], "status")
            self.assertEqual(calls[3][0], "processed")
            self.assertEqual(calls[3][1]["event_type"], "document.processed")

    def test_resolves_processed_topic_from_di_document_processed_pubsub_topic(self) -> None:
        result = MagicMock(spec=ProcessingResult)
        result.status_events = [{"event_type": "document.processing_status.updated", "x": 1}]
        result.document_processed_event = {"event_type": "document.processed"}
        instance = MagicMock()
        with patch.dict(
            os.environ,
            {
                "DI_GCP_PROJECT_ID": "p1",
                "DI_DOCUMENT_PROCESSED_PUBSUB_TOPIC": "custom-processed",
                "DI_STATUS_TOPIC_NAME": "custom-status",
            },
            clear=False,
        ):
            with patch(
                "document_intelligence.processing_runtime.PubSubEventPublisher",
                return_value=instance,
            ) as ctor:
                publish_processing_result_to_pubsub(result)
            cfg = ctor.call_args[0][0]
            self.assertEqual(cfg.processed_topic_name, "custom-processed")
            self.assertEqual(cfg.status_topic_name, "custom-status")
        instance.publish_status_event.assert_called_once()
        instance.publish_document_processed_event.assert_called_once()
