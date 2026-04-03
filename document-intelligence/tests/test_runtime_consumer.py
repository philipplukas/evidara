"""HTTP tests for the internal DI runtime ingress service."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

try:
    from starlette.testclient import TestClient

    from document_intelligence.consumer.app import create_app
except ImportError:
    TestClient = None  # type: ignore[misc, assignment]
    create_app = None  # type: ignore[misc, assignment]

from support import (
    build_bundle_event,
    build_manifest_payload,
    build_pubsub_push_envelope,
)


@unittest.skipUnless(TestClient is not None, "Install document-intelligence[service] for HTTP tests")
class TestRuntimeConsumerHTTP(unittest.TestCase):
    def test_health_sets_generated_correlation_headers(self) -> None:
        client = TestClient(create_app())
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("X-Correlation-Id"))
        self.assertEqual(
            response.headers.get("X-Correlation-Id"),
            response.headers.get("X-Request-ID"),
        )

    def test_health_reuses_incoming_correlation_header(self) -> None:
        client = TestClient(create_app())
        response = client.get("/health", headers={"X-Correlation-Id": "corr_ingest_123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Correlation-Id"), "corr_ingest_123")
        self.assertEqual(response.headers.get("X-Request-ID"), "corr_ingest_123")

    def _build_event_payload(self, temp_dir: str) -> dict[str, object]:
        artifact_path = os.path.join(temp_dir, "document.html")
        manifest_path = os.path.join(temp_dir, "bundle-manifest.json")
        with open(artifact_path, "w", encoding="utf-8") as artifact_file:
            artifact_file.write(
                "<html><head><title>Ingress Doc</title></head><body><h1>Intro</h1><p>Body</p></body></html>"
            )
        with open(manifest_path, "w", encoding="utf-8") as manifest_file:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                ),
                manifest_file,
            )
        return build_bundle_event(manifest_path)

    def test_processes_raw_artifact_bundle_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["DI_SURFACES_ROOT_URI"] = os.path.join(temp_dir, "delta_surfaces")
            try:
                client = TestClient(create_app())
                response = client.post(
                    "/internal/events/artifact-bundles:process",
                    json=self._build_event_payload(temp_dir),
                )
            finally:
                del os.environ["DI_SURFACES_ROOT_URI"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")
        self.assertEqual(response.json()["sections"], 1)
        self.assertIn("document_id", response.json())
        self.assertIn("processing_manifest_id", response.json())

    def test_processes_pubsub_push_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["DI_SURFACES_ROOT_URI"] = os.path.join(temp_dir, "delta_surfaces")
            try:
                client = TestClient(create_app())
                response = client.post(
                    "/internal/events/artifact-bundles:process",
                    json=build_pubsub_push_envelope(self._build_event_payload(temp_dir)),
                )
            finally:
                del os.environ["DI_SURFACES_ROOT_URI"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "processed")
        self.assertEqual(response.json()["sections"], 1)

    def test_rejects_invalid_event_envelope(self) -> None:
        client = TestClient(create_app())
        response = client.post(
            "/internal/events/artifact-bundles:process",
            json={"message": {"data": "not-base64"}},
        )

        self.assertEqual(response.status_code, 400)

    def test_ingest_bearer_required_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["DOCUMENT_INTELLIGENCE_INGEST_BEARER_TOKEN"] = "secret-ingest-token"
            os.environ["DI_SURFACES_ROOT_URI"] = os.path.join(temp_dir, "delta_surfaces")
            try:
                client = TestClient(create_app())
                payload = self._build_event_payload(temp_dir)
                unauthorized = client.post(
                    "/internal/events/artifact-bundles:process",
                    json=payload,
                )
                authorized = client.post(
                    "/internal/events/artifact-bundles:process",
                    json=payload,
                    headers={"Authorization": "Bearer secret-ingest-token"},
                )
            finally:
                del os.environ["DOCUMENT_INTELLIGENCE_INGEST_BEARER_TOKEN"]
                del os.environ["DI_SURFACES_ROOT_URI"]

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)

    def test_requires_surface_configuration_for_default_processor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = TestClient(create_app(), raise_server_exceptions=False)
            response = client.post(
                "/internal/events/artifact-bundles:process",
                json=self._build_event_payload(temp_dir),
            )

        self.assertEqual(response.status_code, 500)
