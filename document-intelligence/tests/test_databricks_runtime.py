import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import yaml

from document_intelligence.jobs.databricks_process_event import run
from support import (
    build_bundle_event,
    build_manifest_payload,
    build_pubsub_push_envelope,
)


DELTA_AVAILABLE = importlib.util.find_spec("deltalake") is not None


def _write_local_bundle_event_fixture(temp_dir: str) -> dict[str, object]:
    html = (
        "<html><head><title>Bundle Job Doc</title></head><body><h1>Scope</h1>"
        "<p>Body</p></body></html>"
    )
    artifact_path = os.path.join(temp_dir, "document.html")
    manifest_path = os.path.join(temp_dir, "bundle-manifest.json")

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

    return build_bundle_event(manifest_path)


class DatabricksBundleConfigTests(unittest.TestCase):
    def test_bundle_and_job_files_have_expected_runtime_shape(self) -> None:
        bundle_path = os.path.join(
            os.path.dirname(__file__), "..", "databricks.yml"
        )
        process_resource_path = os.path.join(
            os.path.dirname(__file__), "..", "resources", "document_intelligence_job.yml"
        )
        autoloader_resource_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "resources",
            "document_intelligence_autoloader_job.yml",
        )
        dbt_resource_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "resources",
            "document_intelligence_dbt_job.yml",
        )
        smoke_resource_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "resources",
            "document_intelligence_smoke_job.yml",
        )

        with open(bundle_path, "r", encoding="utf-8") as bundle_file:
            bundle_config = yaml.safe_load(bundle_file)
        with open(process_resource_path, "r", encoding="utf-8") as resource_file:
            process_resource_config = yaml.safe_load(resource_file)
        with open(autoloader_resource_path, "r", encoding="utf-8") as resource_file:
            autoloader_resource_config = yaml.safe_load(resource_file)
        with open(dbt_resource_path, "r", encoding="utf-8") as resource_file:
            dbt_resource_config = yaml.safe_load(resource_file)
        with open(smoke_resource_path, "r", encoding="utf-8") as resource_file:
            smoke_resource_config = yaml.safe_load(resource_file)

        self.assertEqual(bundle_config["bundle"]["name"], "document-intelligence")
        self.assertEqual(
            bundle_config["artifacts"]["document_intelligence_wheel"]["type"], "whl"
        )
        self.assertIn("dev", bundle_config["targets"])
        self.assertIn("staging", bundle_config["targets"])
        self.assertIn("prod", bundle_config["targets"])
        self.assertIn("catalog", bundle_config["variables"])
        self.assertIn("gcs_processed_bucket", bundle_config["variables"])

        job = process_resource_config["resources"]["jobs"]["document_intelligence_process_bundle"]
        task = job["tasks"][0]
        self.assertEqual(
            task["python_wheel_task"]["entry_point"], "databricks_process_event"
        )
        self.assertEqual(
            task["python_wheel_task"]["package_name"], "document-intelligence"
        )
        self.assertIn("parser_backend", bundle_config["variables"])
        self.assertIn("enable_spacy", bundle_config["variables"])
        self.assertIn("spacy_model_name", bundle_config["variables"])
        self.assertIn("spacy_max_chars_per_section", bundle_config["variables"])
        self.assertIn("spacy_batch_size", bundle_config["variables"])
        named_parameters = task["python_wheel_task"]["named_parameters"]
        self.assertIn("parser_backend", named_parameters)
        self.assertIn("enable_spacy", named_parameters)
        self.assertIn("spacy_model_name", named_parameters)
        self.assertIn("spacy_max_chars_per_section", named_parameters)
        self.assertIn("spacy_batch_size", named_parameters)

        autoloader_jobs = autoloader_resource_config["resources"]["jobs"]
        self.assertIn("document_intelligence_autoloader_bronze", autoloader_jobs)
        dbt_jobs = dbt_resource_config["resources"]["jobs"]
        self.assertIn("document_intelligence_dbt_transformations", dbt_jobs)
        smoke_jobs = smoke_resource_config["resources"]["jobs"]
        self.assertIn("document_intelligence_smoke_test", smoke_jobs)

    def test_bundle_targets_match_environment_tfvars(self) -> None:
        bundle_path = os.path.join(os.path.dirname(__file__), "..", "databricks.yml")
        env_root = os.path.join(os.path.dirname(__file__), "..", "..", "infra", "env")

        with open(bundle_path, "r", encoding="utf-8") as bundle_file:
            bundle_config = yaml.safe_load(bundle_file)

        for environment in ("dev", "staging", "prod"):
            with self.subTest(environment=environment):
                tfvars_path = os.path.join(
                    env_root, environment, "document_intelligence.databricks.tfvars"
                )
                with open(tfvars_path, "r", encoding="utf-8") as tfvars_file:
                    tfvars_body = tfvars_file.read()

                target = bundle_config["targets"][environment]
                self.assertEqual(
                    target["variables"]["workspace_host"],
                    _read_tfvars_string(tfvars_body, "workspace_host"),
                )
                self.assertEqual(
                    target["variables"]["surfaces_root_uri"],
                    _read_tfvars_string(tfvars_body, "external_location_url"),
                )
                self.assertEqual(target["workspace"]["host"], "${var.workspace_host}")


def _read_tfvars_string(tfvars_body: str, field_name: str) -> str:
    match = re.search(
        r'^\s*{field}\s*=\s*"([^"]+)"\s*$'.format(field=re.escape(field_name)),
        tfvars_body,
        re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"Could not find {field_name} in tfvars body")
    return match.group(1)


@unittest.skipUnless(DELTA_AVAILABLE, "deltalake is not installed")
class DatabricksRuntimeIntegrationTests(unittest.TestCase):
    def test_run_writes_delta_outputs_from_local_event_fixture(self) -> None:
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = os.path.join(temp_dir, "event.json")
            surfaces_root_uri = os.path.join(temp_dir, "delta_surfaces")

            with open(event_path, "w", encoding="utf-8") as event_file:
                json.dump(_write_local_bundle_event_fixture(temp_dir), event_file)

            output = run(
                event_path=event_path,
                processing_version="di_2026_03_29",
                surfaces_root_uri=surfaces_root_uri,
            )

            self.assertEqual(output["sections"], 1)
            self.assertTrue(
                output["published_documents_uri"].endswith("published_documents")
            )

            document_rows = (
                deltalake.DeltaTable(
                    os.path.join(surfaces_root_uri, "published_documents")
                )
                .to_pyarrow_table()
                .to_pylist()
            )
            self.assertEqual(len(document_rows), 1)
            self.assertEqual(document_rows[0]["title"], "Bundle Job Doc")

    def test_run_writes_delta_outputs_from_pubsub_push_fixture(self) -> None:
        import deltalake

        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = os.path.join(temp_dir, "pubsub-event.json")
            surfaces_root_uri = os.path.join(temp_dir, "delta_surfaces")

            with open(event_path, "w", encoding="utf-8") as event_file:
                json.dump(
                    build_pubsub_push_envelope(
                        _write_local_bundle_event_fixture(temp_dir)
                    ),
                    event_file,
                )

            output = run(
                event_path=event_path,
                processing_version="di_2026_03_29",
                surfaces_root_uri=surfaces_root_uri,
            )

            self.assertEqual(output["sections"], 1)

            document_rows = (
                deltalake.DeltaTable(
                    os.path.join(surfaces_root_uri, "published_documents")
                )
                .to_pyarrow_table()
                .to_pylist()
            )
            self.assertEqual(len(document_rows), 1)
            self.assertEqual(document_rows[0]["title"], "Bundle Job Doc")


if __name__ == "__main__":
    unittest.main()
