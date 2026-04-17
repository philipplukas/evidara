from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_connector_worker_runtime.py"
SPEC = importlib.util.spec_from_file_location("check_connector_worker_runtime", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load script module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ConnectorWorkerRuntimeCheckTests(unittest.TestCase):
    def _service(
        self,
        name: str,
        *,
        dispatch_backend: str = "worker",
        min_scale: str = "1",
        max_scale: str = "1",
        artifact_store_backend: str = "gcs",
    ):
        return MODULE.ServiceConfig(
            name=name,
            env={
                "PLATFORM_CONTROL_RUN_DISPATCH_BACKEND": dispatch_backend,
                "PLATFORM_CONTROL_GCP_PROJECT_ID": "project-dacd6b7b-dc96-4534-b82",
                "PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND": artifact_store_backend,
                "PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND": "pubsub",
                "PLATFORM_CONTROL_RAW_ARTIFACT_BUCKET": "evidara-raw-artifacts-dev",
                "PLATFORM_CONTROL_RAW_ARTIFACT_PUBSUB_TOPIC": "raw-artifact-available",
                "PLATFORM_CONTROL_ARTIFACT_BUNDLE_PUBSUB_TOPIC": "artifact-bundle-available",
            },
            secret_env={"PLATFORM_CONTROL_DATABASE_URL": "platform-control-database-url-dev"},
            annotations={
                "autoscaling.knative.dev/minScale": min_scale,
                "autoscaling.knative.dev/maxScale": max_scale,
                "run.googleapis.com/cloudsql-instances": "project:region:instance",
            },
        )

    def test_evaluate_passes_for_aligned_worker_backed_runtime(self) -> None:
        api = self._service("platform-control-api-dev")
        worker = self._service("platform-control-worker-dev")

        self.assertEqual(MODULE.evaluate(api, worker), [])

    def test_evaluate_fails_when_api_is_not_worker_backed(self) -> None:
        api = self._service("platform-control-api-dev", dispatch_backend="inline")
        worker = self._service("platform-control-worker-dev")

        errors = MODULE.evaluate(api, worker)

        self.assertIn(
            "platform-control-api-dev: expected PLATFORM_CONTROL_RUN_DISPATCH_BACKEND=worker, found inline.",
            errors,
        )

    def test_evaluate_fails_when_worker_scaling_and_env_parity_drift(self) -> None:
        api = self._service("platform-control-api-dev")
        worker = self._service(
            "platform-control-worker-dev",
            min_scale="0",
            max_scale="2",
            artifact_store_backend="local",
        )

        errors = MODULE.evaluate(api, worker)

        self.assertIn(
            "API/worker drift for PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND: api=gcs, worker=local.",
            errors,
        )
        self.assertIn(
            "platform-control-worker-dev: expected minScale=1, found 0.",
            errors,
        )
        self.assertIn(
            "platform-control-worker-dev: expected maxScale=1, found 2.",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
