"""Delta -> OpenSearch backfill (issue #552, ADR-0005).

Proves the two halves of the recovery path that did not exist before:

1. a canonical ``published_documents`` row can be turned back into a *contract-valid*
   ``document.processed`` event (so a lost index is rebuildable from Delta alone), and
2. the backfill loop is idempotent-friendly, resumable, and does not abort a whole corpus
   on one bad or rejected document.
"""

import contextlib
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.errors import ProcessingError
from document_intelligence.events.document_processed import (
    build_document_processed_event_from_published_row,
)
from document_intelligence.jobs.delta_projection_backfill import (
    FileCheckpoint,
    backfill_rows,
)
from document_intelligence.jobs.projection_bridge_consumer import PermanentForwardError
from document_intelligence.validate.schema_validation import validate_instance_against_contract
from support import RUN_ID, SOURCE_ID, SOURCE_VERSION_ID

DELTA_AVAILABLE = importlib.util.find_spec("deltalake") is not None

DOC_ID = "doc_01jq7bdptzqv3xs0c41xpw1ybg"
DOC_ID_2 = "doc_01jq7bdptzqv3xs0c41xpw1ybh"
PM_ID = "pm_01jq7bhgy7g0pkj4f1d03f8f8c"


def published_row(**overrides: Any) -> dict[str, Any]:
    """A row shaped like `published_documents` on canonical Delta."""
    row: dict[str, Any] = {
        "document_id": DOC_ID,
        "document_revision": 1,
        "processing_manifest_id": PM_ID,
        "processing_version": "di_2026_03_29",
        "provenance": {
            "tenant_id": "tenant_public",
            "corpus_id": "corpus_ch_fedlex",
            "scope_type": "global_public",
            "source_id": SOURCE_ID,
            "source_version_id": SOURCE_VERSION_ID,
            "run_id": RUN_ID,
        },
        "authority_id": "auth_fedlex",
        "lifecycle_status": "active",
        "metadata": {
            "source_origin_kind": "official_primary",
            "source_defaults": {"authority_name": "Fedlex"},
        },
    }
    row.update(overrides)
    return row


class RebuildEventFromCanonicalRowTests(unittest.TestCase):
    def test_rebuilt_event_satisfies_the_document_processed_contract(self) -> None:
        event = build_document_processed_event_from_published_row(published_row())

        # The whole point of #552: canonical Delta alone is enough to emit a valid event.
        validate_instance_against_contract(event, "events/document-processed.schema.json")

        self.assertEqual(event["event_type"], "document.processed")
        self.assertEqual(event["producer"], "document-intelligence")
        payload = event["payload"]
        self.assertEqual(payload["document_id"], DOC_ID)
        self.assertEqual(payload["document_revision"], 1)
        self.assertEqual(payload["processing_manifest_id"], PM_ID)
        self.assertEqual(payload["lifecycle_status"], "active")

    def test_authority_and_officialness_are_rederived_from_persisted_metadata(self) -> None:
        payload = build_document_processed_event_from_published_row(published_row())["payload"]
        self.assertEqual(payload["authority_id"], "auth_fedlex")
        self.assertEqual(payload["authority_name"], "Fedlex")
        self.assertTrue(payload["is_official"])

        unofficial = build_document_processed_event_from_published_row(
            published_row(metadata={"source_origin_kind": "third_party"})
        )["payload"]
        self.assertFalse(unofficial["is_official"])
        self.assertIsNone(unofficial["authority_name"])

    def test_surface_refs_are_reconstructed_without_reading_the_manifest_table(self) -> None:
        payload = build_document_processed_event_from_published_row(published_row())["payload"]
        self.assertEqual(
            payload["published_document_ref"],
            {
                "surface_name": "published_documents",
                "surface_version": 1,
                "record_key": {"document_id": DOC_ID, "processing_manifest_id": PM_ID},
            },
        )
        self.assertEqual(
            payload["published_sections_ref"],
            {
                "surface_name": "published_sections",
                "surface_version": 1,
                "record_filter": {"document_id": DOC_ID, "processing_manifest_id": PM_ID},
            },
        )
        self.assertEqual(payload["processing_manifest_ref"]["manifest_id"], PM_ID)

    def test_correlation_id_defaults_to_the_run_that_produced_the_document(self) -> None:
        event = build_document_processed_event_from_published_row(published_row())
        self.assertEqual(event["correlation_id"], RUN_ID)

    def test_each_emission_gets_a_fresh_event_id(self) -> None:
        # A surviving projection-history index must never dedupe a rebuild of an empty
        # documents index, so backfill events cannot reuse a stable event_id.
        first = build_document_processed_event_from_published_row(published_row())
        second = build_document_processed_event_from_published_row(published_row())
        self.assertNotEqual(first["event_id"], second["event_id"])

    def test_unusable_rows_raise_rather_than_emit_a_broken_event(self) -> None:
        for broken in (
            published_row(provenance=None),
            published_row(document_revision=0),
            published_row(processing_manifest_id=""),
            published_row(lifecycle_status=None),
        ):
            with self.assertRaises(ProcessingError):
                build_document_processed_event_from_published_row(broken)


class RecordingPoster:
    def __init__(self, fail_with: dict[str, list[Exception]] | None = None) -> None:
        self.posted: list[dict[str, Any]] = []
        self._fail_with = fail_with or {}

    def __call__(self, event: dict[str, Any]) -> None:
        document_id = event["payload"]["document_id"]
        pending = self._fail_with.get(document_id)
        if pending:
            raise pending.pop(0)
        self.posted.append(event)


class BackfillLoopTests(unittest.TestCase):
    def test_posts_one_event_per_document_and_reports_progress(self) -> None:
        poster = RecordingPoster()
        applied: list[str] = []

        summary = backfill_rows(
            [published_row(), published_row(document_id=DOC_ID_2)],
            post=poster,
            on_applied=applied.append,
        )

        self.assertEqual(summary.scanned, 2)
        self.assertEqual(summary.applied, 2)
        self.assertFalse(summary.failed)
        self.assertEqual(summary.last_document_id, DOC_ID_2)
        self.assertEqual([e["payload"]["document_id"] for e in poster.posted], [DOC_ID, DOC_ID_2])
        self.assertEqual(applied, [DOC_ID, DOC_ID_2])

    def test_dry_run_posts_nothing(self) -> None:
        poster = RecordingPoster()
        summary = backfill_rows([published_row()], post=poster, dry_run=True)

        self.assertEqual(poster.posted, [])
        self.assertEqual(summary.applied, 1)
        self.assertTrue(summary.dry_run)

    def test_limit_stops_early(self) -> None:
        poster = RecordingPoster()
        summary = backfill_rows(
            [published_row(), published_row(document_id=DOC_ID_2)],
            post=poster,
            limit=1,
        )

        self.assertEqual(summary.scanned, 1)
        self.assertEqual(len(poster.posted), 1)

    def test_a_rejected_document_does_not_strand_the_rest_of_the_corpus(self) -> None:
        poster = RecordingPoster(fail_with={DOC_ID: [PermanentForwardError("rejected 400")]})

        summary = backfill_rows(
            [published_row(), published_row(document_id=DOC_ID_2)],
            post=poster,
            max_retries=2,
            sleep=lambda _: None,
        )

        self.assertEqual(summary.rejected, 1)
        self.assertEqual(summary.applied, 1)
        self.assertFalse(summary.failed)
        self.assertEqual([e["payload"]["document_id"] for e in poster.posted], [DOC_ID_2])

    def test_an_invalid_row_is_skipped_not_fatal(self) -> None:
        poster = RecordingPoster()

        summary = backfill_rows(
            [published_row(provenance=None), published_row(document_id=DOC_ID_2)],
            post=poster,
            sleep=lambda _: None,
        )

        self.assertEqual(summary.skipped_invalid, 1)
        self.assertEqual(summary.invalid_document_ids, [DOC_ID])
        self.assertEqual(summary.applied, 1)
        self.assertFalse(summary.failed)

    def test_transient_failures_are_retried(self) -> None:
        poster = RecordingPoster(fail_with={DOC_ID: [RuntimeError("503"), RuntimeError("503")]})
        delays: list[float] = []

        summary = backfill_rows(
            [published_row()],
            post=poster,
            max_retries=3,
            retry_backoff_seconds=1.0,
            sleep=delays.append,
        )

        self.assertEqual(summary.applied, 1)
        self.assertFalse(summary.failed)
        self.assertEqual(delays, [1.0, 2.0])

    def test_exhausted_retries_fail_the_run_but_keep_the_completed_prefix(self) -> None:
        poster = RecordingPoster(fail_with={DOC_ID_2: [RuntimeError("503")] * 5})
        applied: list[str] = []

        summary = backfill_rows(
            [published_row(), published_row(document_id=DOC_ID_2)],
            post=poster,
            on_applied=applied.append,
            max_retries=2,
            sleep=lambda _: None,
        )

        self.assertTrue(summary.failed)
        self.assertIsNotNone(summary.failure_reason)
        # The first document stays checkpointed, so --resume continues from it.
        self.assertEqual(summary.applied, 1)
        self.assertEqual(summary.last_document_id, DOC_ID)
        self.assertEqual(applied, [DOC_ID])


class FileCheckpointTests(unittest.TestCase):
    def test_records_and_reads_back_the_resume_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = FileCheckpoint(Path(temp_dir) / "nested" / "cursor")
            self.assertIsNone(checkpoint.read())

            checkpoint.record(DOC_ID)
            self.assertEqual(checkpoint.read(), DOC_ID)

            checkpoint.clear()
            self.assertIsNone(checkpoint.read())


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class CanonicalDeltaEnumerationTests(unittest.TestCase):
    """The end-to-end claim of #552: canonical Delta on disk -> replayable events."""

    def test_enumerates_the_latest_revision_of_each_published_document(self) -> None:
        from document_intelligence.persist.sinks import DeltaCanonicalSink, DeltaSinkConfig
        from document_intelligence.service.store import DeltaPublishedDocumentStore
        from test_adapters import build_processing_result

        with tempfile.TemporaryDirectory() as temp_dir:
            documents_uri = os.path.join(temp_dir, "published_documents")
            sections_uri = os.path.join(temp_dir, "published_sections")
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=documents_uri,
                    published_sections_uri=sections_uri,
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )

            result = build_processing_result()
            sink.persist(result.document, result.sections, result.manifest)

            # A second revision of the same logical document supersedes the first.
            revised_manifest_id = "pm_01jq7bhgy7g0pkj4f1d03f8f8d"
            revised = replace(
                result.document,
                document_revision=2,
                processing_manifest_id=revised_manifest_id,
                title="Revised Delta Doc",
            )
            sink.persist(
                revised,
                result.sections,
                replace(
                    result.manifest,
                    processing_manifest_id=revised_manifest_id,
                    document_revision=2,
                ),
            )

            store = DeltaPublishedDocumentStore(documents_uri, sections_uri)
            rows = list(store.iter_latest_document_rows())

            self.assertEqual(len(rows), 1, "one logical document, latest revision only")
            self.assertEqual(rows[0]["document_id"], result.document.document_id)
            self.assertEqual(rows[0]["document_revision"], 2)
            self.assertEqual(rows[0]["processing_manifest_id"], revised_manifest_id)

            # Heavy body columns are deliberately not pulled into memory.
            self.assertNotIn("full_text", rows[0])

            # And the canonical row replays as a contract-valid event.
            event = build_document_processed_event_from_published_row(rows[0])
            validate_instance_against_contract(event, "events/document-processed.schema.json")
            self.assertEqual(event["payload"]["document_revision"], 2)

            # The resume cursor excludes everything at or before the given document_id.
            self.assertEqual(
                list(store.iter_latest_document_rows(after_document_id=result.document.document_id)),
                [],
            )

    def test_backfill_replays_a_delta_corpus_into_the_projections_endpoint(self) -> None:
        from document_intelligence.persist.sinks import DeltaCanonicalSink, DeltaSinkConfig
        from document_intelligence.service.store import DeltaPublishedDocumentStore
        from test_adapters import build_processing_result

        with tempfile.TemporaryDirectory() as temp_dir:
            documents_uri = os.path.join(temp_dir, "published_documents")
            sections_uri = os.path.join(temp_dir, "published_sections")
            sink = DeltaCanonicalSink(
                DeltaSinkConfig(
                    published_documents_uri=documents_uri,
                    published_sections_uri=sections_uri,
                    processing_manifests_uri=os.path.join(temp_dir, "processing_manifests"),
                )
            )
            result = build_processing_result()
            sink.persist(result.document, result.sections, result.manifest)

            store = DeltaPublishedDocumentStore(documents_uri, sections_uri)
            poster = RecordingPoster()
            summary = backfill_rows(store.iter_latest_document_rows(), post=poster)

            self.assertEqual(summary.applied, 1)
            self.assertEqual(summary.skipped_invalid, 0)
            self.assertEqual(len(poster.posted), 1)
            self.assertEqual(
                poster.posted[0]["payload"]["document_id"],
                result.document.document_id,
            )
            # The bridge ships raw JSON bytes; the rebuilt event must survive that.
            json.dumps(poster.posted[0])


class _AcceptEverythingProjections(http.server.BaseHTTPRequestHandler):
    """Stand-in for the legal-search projections endpoint: accepts every event."""

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
        self.rfile.read(int(self.headers.get("content-length") or 0))
        self.send_response(202)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"applied"}')

    def log_message(self, *args: Any) -> None:
        return


@contextlib.contextmanager
def _projections_endpoint() -> Any:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _AcceptEverythingProjections)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class BackfillProcessExitCodeTests(unittest.TestCase):
    """The job's *exit code* must agree with its summary (#825).

    The backfill used to print ``"failed": false`` and then abort with ``terminate called
    without an active exception`` while the interpreter was shutting down — exit 134/139, so a
    Kubernetes Job reported ``Failed`` and a ``set -e`` runbook step stopped, on a run that had
    already done its work. The crash lived in the Delta/Arrow teardown *after* ``main()``
    returned, which is why no in-process test could see it: calling ``main()`` and asserting on
    its return value passed throughout. Only a real subprocess exposes it.

    The pre-fix abort is a race, not a certainty: measured at 15/30 runs for ``--dry-run`` on a
    local table and 6/20 against MinIO. Repeating the invocation is therefore part of the
    assertion — one clean run proves nothing.
    """

    RUNS = 8

    def _corpus(self, temp_dir: str) -> dict[str, str]:
        from document_intelligence.persist.sinks import DeltaCanonicalSink, DeltaSinkConfig
        from test_adapters import build_processing_result

        uris = {
            "DI_PUBLISHED_DOCUMENTS_URI": os.path.join(temp_dir, "published_documents"),
            "DI_PUBLISHED_SECTIONS_URI": os.path.join(temp_dir, "published_sections"),
            "DI_PROCESSING_MANIFESTS_URI": os.path.join(temp_dir, "processing_manifests"),
        }
        sink = DeltaCanonicalSink(
            DeltaSinkConfig(
                published_documents_uri=uris["DI_PUBLISHED_DOCUMENTS_URI"],
                published_sections_uri=uris["DI_PUBLISHED_SECTIONS_URI"],
                processing_manifests_uri=uris["DI_PROCESSING_MANIFESTS_URI"],
            )
        )
        result = build_processing_result()
        sink.persist(result.document, result.sections, result.manifest)
        return uris

    def _run(self, uris: dict[str, str], argv: list[str]) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, **uris)
        env["PYTHONPATH"] = os.pathsep.join(
            [os.path.join(os.path.dirname(__file__), "..", "src"), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        return subprocess.run(
            [sys.executable, "-m", "document_intelligence.jobs.delta_projection_backfill", *argv],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    def _assert_clean_exit(self, completed: subprocess.CompletedProcess[str], attempt: int) -> None:
        self.assertEqual(
            completed.returncode,
            0,
            f"run {attempt} exited {completed.returncode}; stderr tail: {completed.stderr[-2000:]}",
        )
        self.assertNotIn("terminate called", completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["failed"], False)

    def test_dry_run_exits_zero_every_time(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            uris = self._corpus(temp_dir)
            for attempt in range(1, self.RUNS + 1):
                completed = self._run(uris, ["--dry-run"])
                self._assert_clean_exit(completed, attempt)
                self.assertEqual(json.loads(completed.stdout)["applied"], 1)

    def test_real_run_exits_zero_every_time(self) -> None:
        """The POST path, which the issue explicitly refused to call proven.

        Be honest about what this one is worth: reverting the fix leaves it green (0/30 aborts
        measured), because the HTTP round-trips give teardown enough slack to win the race. It
        is a guard against the *next* change tipping that balance, not a reproducer.
        """
        with tempfile.TemporaryDirectory() as temp_dir, _projections_endpoint() as url:
            uris = self._corpus(temp_dir)
            checkpoint = os.path.join(temp_dir, "checkpoint")
            for attempt in range(1, self.RUNS + 1):
                completed = self._run(
                    uris,
                    ["--legal-search-api-url", url, "--checkpoint-path", checkpoint],
                )
                self._assert_clean_exit(completed, attempt)
                self.assertEqual(json.loads(completed.stdout)["applied"], 1)


class NativeDeltaFilesystemTests(unittest.TestCase):
    """``delta_dataset_filesystem`` must produce a native filesystem, or nothing at all."""

    def test_local_uri_resolves_to_a_native_filesystem_rooted_at_the_table(self) -> None:
        import pyarrow.fs as pa_fs

        from document_intelligence.persist.sinks import delta_dataset_filesystem

        with tempfile.TemporaryDirectory() as temp_dir:
            filesystem = delta_dataset_filesystem(temp_dir)

        self.assertIsInstance(filesystem, pa_fs.SubTreeFileSystem)
        # A PyFileSystem here would mean Arrow's IO threads call back into Python — the
        # teardown abort in #825. LocalFileSystem is entirely C++.
        self.assertIsInstance(filesystem.base_fs, pa_fs.LocalFileSystem)

    def test_s3_endpoint_options_are_mirrored_onto_a_native_s3_filesystem(self) -> None:
        import pyarrow.fs as pa_fs

        from document_intelligence.persist.sinks import delta_dataset_filesystem, delta_storage_options

        options = delta_storage_options(
            {
                "DI_S3_ENDPOINT_URL": "http://minio.evidara.svc:9000",
                "DI_S3_REGION": "us-east-1",
                "DI_S3_ACCESS_KEY_ID": "key",
                "DI_S3_SECRET_ACCESS_KEY": "secret",
            }
        )
        filesystem = delta_dataset_filesystem("s3://canonical/published_documents", options)

        self.assertIsInstance(filesystem, pa_fs.SubTreeFileSystem)
        self.assertIsInstance(filesystem.base_fs, pa_fs.S3FileSystem)
        # Rooted at the table, because to_pyarrow_dataset() resolves fragments relatively.
        self.assertEqual(filesystem.base_path, "canonical/published_documents/")

    def test_an_unresolvable_uri_falls_back_to_deltalake_s_own_handler(self) -> None:
        from document_intelligence.persist.sinks import delta_dataset_filesystem

        self.assertIsNone(delta_dataset_filesystem("nosuchscheme://bucket/table"))


if __name__ == "__main__":
    unittest.main()
