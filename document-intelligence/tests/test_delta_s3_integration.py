"""Opt-in integration test: the Delta read path against a real S3-compatible store (#825).

`s3://` + `DI_S3_ENDPOINT_URL` (MinIO) is the shape the self-hosted deployment actually runs,
and it is the only branch of `delta_dataset_filesystem` that production takes. The unit tests
in `test_delta_projection_backfill.py` assert the filesystem is *constructed* with the right
endpoint, scheme and region — they cannot assert that it reads. Asserting on a constructed type
while the real backend is never touched is exactly how #675 / #713 shipped green over nothing.

This test writes a canonical corpus to MinIO, reads it back through
`DeltaPublishedDocumentStore`, and runs the backfill entrypoint as a subprocess several times to
assert the *exit code* — the teardown abort this fix is about only exists in a real process.

Gated on ``EVIDARA_MINIO_IT=1`` and the ``it`` extra (testcontainers + Docker), so it skips
cleanly everywhere else:

    cd document-intelligence
    EVIDARA_MINIO_IT=1 uv run --extra it --extra test pytest tests/test_delta_s3_integration.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

try:
    import boto3
    from botocore.client import Config
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    _HAVE_DEPS = True
except Exception:  # pragma: no cover - optional integration deps
    _HAVE_DEPS = False

_RUN_IT = os.environ.get("EVIDARA_MINIO_IT") == "1"

BUCKET = "canonical"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"
RUNS = 5


@unittest.skipUnless(_RUN_IT and _HAVE_DEPS, "set EVIDARA_MINIO_IT=1 and install [it] extra (Docker required)")
class DeltaOverMinioIntegrationTests(unittest.TestCase):
    def test_reads_and_exits_cleanly_against_a_real_object_store(self) -> None:
        container = (
            DockerContainer("quay.io/minio/minio:latest")
            .with_command("server /data")
            .with_env("MINIO_ROOT_USER", ACCESS_KEY)
            .with_env("MINIO_ROOT_PASSWORD", SECRET_KEY)
            .with_exposed_ports(9000)
        )
        container.start()
        try:
            wait_for_logs(container, "API:", timeout=60)
            endpoint = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"
            self._create_bucket(endpoint)
            env = self._environment(endpoint)
            self._write_corpus(env)
            self._assert_store_reads_over_s3(env)
            self._assert_entrypoint_exits_zero(env)
        finally:
            container.stop()

    def _create_bucket(self, endpoint: str) -> None:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name="us-east-1",
            config=Config(signature_version="s3v4"),
        )
        client.create_bucket(Bucket=BUCKET)

    def _environment(self, endpoint: str) -> dict[str, str]:
        return {
            "DI_PUBLISHED_DOCUMENTS_URI": f"s3://{BUCKET}/published_documents",
            "DI_PUBLISHED_SECTIONS_URI": f"s3://{BUCKET}/published_sections",
            "DI_PROCESSING_MANIFESTS_URI": f"s3://{BUCKET}/processing_manifests",
            "DI_S3_ENDPOINT_URL": endpoint,
            "DI_S3_REGION": "us-east-1",
            "DI_S3_ACCESS_KEY_ID": ACCESS_KEY,
            "DI_S3_SECRET_ACCESS_KEY": SECRET_KEY,
        }

    def _write_corpus(self, env: dict[str, str]) -> None:
        from document_intelligence.persist.sinks import DeltaCanonicalSink, DeltaSinkConfig, delta_storage_options
        from test_adapters import build_processing_result

        self._result = build_processing_result()
        sink = DeltaCanonicalSink(
            DeltaSinkConfig(
                published_documents_uri=env["DI_PUBLISHED_DOCUMENTS_URI"],
                published_sections_uri=env["DI_PUBLISHED_SECTIONS_URI"],
                processing_manifests_uri=env["DI_PROCESSING_MANIFESTS_URI"],
            ),
            storage_options=delta_storage_options(env),
        )
        sink.persist(self._result.document, self._result.sections, self._result.manifest)

    def _assert_store_reads_over_s3(self, env: dict[str, str]) -> None:
        import pyarrow.fs as pa_fs

        from document_intelligence.persist.sinks import delta_dataset_filesystem, delta_storage_options
        from document_intelligence.service.store import DeltaPublishedDocumentStore

        options = delta_storage_options(env)
        filesystem = delta_dataset_filesystem(env["DI_PUBLISHED_DOCUMENTS_URI"], options)
        # The branch under test really is the native one — not deltalake's Python bridge.
        self.assertIsInstance(filesystem, pa_fs.SubTreeFileSystem)
        self.assertIsInstance(filesystem.base_fs, pa_fs.S3FileSystem)

        store = DeltaPublishedDocumentStore(
            env["DI_PUBLISHED_DOCUMENTS_URI"],
            env["DI_PUBLISHED_SECTIONS_URI"],
            storage_options=options,
        )
        rows = list(store.iter_latest_document_rows())
        self.assertEqual([row["document_id"] for row in rows], [self._result.document.document_id])

        # get_full() and _get_sections() take the same path and are what the document service
        # serves per request.
        full = store.get_full(self._result.document.document_id, None)
        self.assertIsNotNone(full)
        self.assertEqual(full["document_id"], self._result.document.document_id)
        self.assertEqual(len(full.get("sections") or []), len(self._result.sections))

    def _assert_entrypoint_exits_zero(self, env: dict[str, str]) -> None:
        process_env = dict(os.environ, **env)
        process_env["PYTHONPATH"] = os.pathsep.join(
            [os.path.join(os.path.dirname(__file__), "..", "src"), process_env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)

        for attempt in range(1, RUNS + 1):
            completed = subprocess.run(
                [sys.executable, "-m", "document_intelligence.jobs.delta_projection_backfill", "--dry-run"],
                env=process_env,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"run {attempt} exited {completed.returncode}; stderr tail: {completed.stderr[-2000:]}",
            )
            self.assertNotIn("terminate called", completed.stderr)
            summary: dict[str, Any] = json.loads(completed.stdout)
            self.assertFalse(summary["failed"])
            self.assertEqual(summary["applied"], 1)


if __name__ == "__main__":
    unittest.main()
