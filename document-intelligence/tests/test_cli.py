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
from support import build_bundle_event, build_manifest_payload


class ProcessEventCliTests(unittest.TestCase):
    def test_cli_processes_local_bundle_fixture(self) -> None:
        html = "<html><head><title>CLI Doc</title></head><body><h1>Intro</h1><p>Body</p></body></html>"
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as html_handle:
            html_handle.write(html)
            artifact_path = html_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as manifest_handle:
            json.dump(
                build_manifest_payload(
                    artifact_path,
                    artifact_role="primary_document",
                ),
                manifest_handle,
            )
            manifest_path = manifest_handle.name

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as event_handle:
            json.dump(build_bundle_event(manifest_path), event_handle)
            event_path = event_handle.name

        stdout_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_buffer):
                exit_code = main([event_path])
        finally:
            os.unlink(artifact_path)
            os.unlink(manifest_path)
            os.unlink(event_path)

        self.assertEqual(exit_code, 0)
        output = json.loads(stdout_buffer.getvalue())
        self.assertIn("document_id", output)
        self.assertIn("processing_manifest_id", output)
        self.assertEqual(output["sections"], 1)


if __name__ == "__main__":
    unittest.main()
