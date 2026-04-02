import importlib.util
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import yaml

from document_intelligence.jobs.databricks_process_event import run
from support import build_bundle_event, build_manifest_payload


DELTA_AVAILABLE = importlib.util.find_spec("deltalake") is not None


class DatabricksBundleConfigTests(unittest.TestCase):
    def test_bundle_and_job_files_have_expected_runtime_shape(self) -> None:
        bundle_path = os.path.join(
            os.path.dirname(__file__), "..", "databricks.yml"
        )
        resource_path = os.path.join(
            os.path.dirname(__file__), "..", "resources", "document_intelligence_job.yml"
        )

        with open(bundle_path, "r", encoding="utf-8") as bundle_file:
            bundle_config = yaml.safe_load(bundle_file)
        with open(resource_path, "r", encoding="utf-8") as resource_file:
            resource_config = yaml.safe_load(resource_file)

        self.assertEqual(bundle_config["bundle"]["name"], "document-intelligence")
        self.assertEqual(
            bundle_config["artifacts"]["document_intelligence_wheel"]["type"], "whl"
        )

        job = resource_config["resources"]["jobs"]["document_intelligence_process_bundle"]
        task = job["tasks"][0]
        self.assertEqual(
            task["python_wheel_task"]["entry_point"], "databricks_process_event"
        )
        self.assertEqual(
            task["python_wheel_task"]["package_name"], "document-intelligence"
        )


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class DatabricksRuntimeIntegrationTests(unittest.TestCase):
    def test_run_writes_delta_outputs_from_local_event_fixture(self) -> None:
        import deltalake

        html = "<html><head><title>Bundle Job Doc</title></head><body><h1>Scope</h1><p>Body</p></body></html>"
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = os.path.join(temp_dir, "document.html")
            manifest_path = os.path.join(temp_dir, "bundle-manifest.json")
            event_path = os.path.join(temp_dir, "event.json")
            surfaces_root_uri = os.path.join(temp_dir, "delta_surfaces")

            with open(artifact_path, "w", encoding="utf-8") as artifact_file:
                artifact_file.write(html)
            with open(manifest_path, "w", encoding="utf-8") as manifest_file:
                json.dump(
                    build_manifest_payload(
                        artifact_path,
                        artifact_role="primary_document",
                    ),
                    manifest_file,
                )
            with open(event_path, "w", encoding="utf-8") as event_file:
                json.dump(build_bundle_event(manifest_path), event_file)

            output = run(
                event_path=event_path,
                processing_version="di_2026_03_29",
                surfaces_root_uri=surfaces_root_uri,
            )

            self.assertEqual(output["sections"], 1)
            self.assertTrue(output["published_documents_uri"].endswith("published_documents"))

            document_rows = deltalake.DeltaTable(
                os.path.join(surfaces_root_uri, "published_documents")
            ).to_pyarrow_table().to_pylist()
            self.assertEqual(len(document_rows), 1)
            self.assertEqual(document_rows[0]["title"], "Bundle Job Doc")


if __name__ == "__main__":
    unittest.main()
