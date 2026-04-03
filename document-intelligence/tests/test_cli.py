import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from document_intelligence.jobs.process_event import main
from support import (
    build_bundle_event,
    build_manifest_payload,
    build_pubsub_push_envelope,
)


def _write_local_bundle_event_fixture(temp_dir: str) -> dict[str, object]:
    html = (
        "<html><head><title>CLI Doc</title></head><body><h1>Intro</h1>"
        "<p>Body</p></body></html>"
    )
    artifact_path = os.path.join(temp_dir, "document.html")
    manifest_path = os.path.join(temp_dir, "bundle-manifest.json")

    with open(artifact_path, "w", encoding="utf-8") as artifact_handle:
        artifact_handle.write(html)
    with open(manifest_path, "w", encoding="utf-8") as manifest_handle:
        json.dump(
            build_manifest_payload(
                artifact_path,
                artifact_role="primary_document",
            ),
            manifest_handle,
        )

    return build_bundle_event(manifest_path)


class ProcessEventCliTests(unittest.TestCase):
    def test_cli_processes_local_bundle_fixture(self) -> None:
        stdout_buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = os.path.join(temp_dir, "event.json")
            with open(event_path, "w", encoding="utf-8") as event_handle:
                json.dump(_write_local_bundle_event_fixture(temp_dir), event_handle)

            with contextlib.redirect_stdout(stdout_buffer):
                exit_code = main([event_path])

        self.assertEqual(exit_code, 0)
        output = json.loads(stdout_buffer.getvalue())
        self.assertIn("document_id", output)
        self.assertIn("processing_manifest_id", output)
        self.assertEqual(output["sections"], 1)

    def test_cli_processes_pubsub_push_envelope_fixture(self) -> None:
        stdout_buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            event_payload = _write_local_bundle_event_fixture(temp_dir)
            event_path = os.path.join(temp_dir, "pubsub-event.json")
            with open(event_path, "w", encoding="utf-8") as event_handle:
                json.dump(build_pubsub_push_envelope(event_payload), event_handle)

            with contextlib.redirect_stdout(stdout_buffer):
                exit_code = main([event_path])

        self.assertEqual(exit_code, 0)
        output = json.loads(stdout_buffer.getvalue())
        self.assertIn("document_id", output)
        self.assertIn("processing_manifest_id", output)
        self.assertEqual(output["sections"], 1)


if __name__ == "__main__":
    unittest.main()
