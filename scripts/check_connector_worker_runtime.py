#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


_API_WORKER_PARITY_VARS = (
    "PLATFORM_CONTROL_GCP_PROJECT_ID",
    "PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND",
    "PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND",
    "PLATFORM_CONTROL_RAW_ARTIFACT_BUCKET",
    "PLATFORM_CONTROL_RAW_ARTIFACT_PUBSUB_TOPIC",
    "PLATFORM_CONTROL_ARTIFACT_BUNDLE_PUBSUB_TOPIC",
)
_DISPATCH_BACKEND_VAR = "PLATFORM_CONTROL_RUN_DISPATCH_BACKEND"
_MIN_SCALE_ANNOTATIONS = (
    "run.googleapis.com/minScale",
    "autoscaling.knative.dev/minScale",
)
_MAX_SCALE_ANNOTATIONS = (
    "run.googleapis.com/maxScale",
    "autoscaling.knative.dev/maxScale",
)
_CLOUDSQL_ANNOTATION = "run.googleapis.com/cloudsql-instances"


@dataclass(frozen=True)
class ServiceConfig:
    name: str
    env: dict[str, str]
    secret_env: dict[str, str]
    annotations: dict[str, str]


def run_cmd(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{detail}")
    return result.stdout


def describe_service(project_id: str, region: str, service_name: str) -> ServiceConfig:
    raw = run_cmd(
        [
            "gcloud",
            "run",
            "services",
            "describe",
            service_name,
            f"--project={project_id}",
            f"--region={region}",
            "--format=json",
        ]
    )
    payload = json.loads(raw)
    root_metadata = payload.get("metadata") or {}
    template = ((payload.get("spec") or {}).get("template") or {})
    metadata = template.get("metadata") or {}
    spec = template.get("spec") or {}
    containers = spec.get("containers") or []
    first_container = containers[0] if containers else {}

    env: dict[str, str] = {}
    secret_env: dict[str, str] = {}
    for item in first_container.get("env") or []:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        if "value" in item and item["value"] is not None:
            env[name] = str(item["value"])
            continue
        secret_ref = ((item.get("valueFrom") or {}).get("secretKeyRef") or {}).get("name")
        if isinstance(secret_ref, str) and secret_ref:
            secret_env[name] = secret_ref

    annotations: dict[str, str] = {}
    for source in (metadata.get("annotations") or {}, root_metadata.get("annotations") or {}):
        for key, value in source.items():
            if isinstance(key, str):
                annotations[key] = str(value)
    return ServiceConfig(
        name=service_name,
        env=env,
        secret_env=secret_env,
        annotations=annotations,
    )


def evaluate(api: ServiceConfig, worker: ServiceConfig) -> list[str]:
    errors: list[str] = []

    api_dispatch = api.env.get(_DISPATCH_BACKEND_VAR)
    if api_dispatch != "worker":
        errors.append(
            f"{api.name}: expected {_DISPATCH_BACKEND_VAR}=worker, found {api_dispatch or '<missing>'}."
        )

    worker_dispatch = worker.env.get(_DISPATCH_BACKEND_VAR)
    if worker_dispatch != "worker":
        errors.append(
            f"{worker.name}: expected {_DISPATCH_BACKEND_VAR}=worker, found {worker_dispatch or '<missing>'}."
        )

    for key in _API_WORKER_PARITY_VARS:
        api_value = api.env.get(key)
        worker_value = worker.env.get(key)
        if api_value != worker_value:
            errors.append(
                f"API/worker drift for {key}: api={api_value or '<missing>'}, worker={worker_value or '<missing>'}."
            )

    api_db_secret = api.secret_env.get("PLATFORM_CONTROL_DATABASE_URL")
    worker_db_secret = worker.secret_env.get("PLATFORM_CONTROL_DATABASE_URL")
    if api_db_secret != worker_db_secret:
        errors.append(
            "API/worker drift for PLATFORM_CONTROL_DATABASE_URL secret: "
            f"api={api_db_secret or '<missing>'}, worker={worker_db_secret or '<missing>'}."
        )

    api_cloudsql = api.annotations.get(_CLOUDSQL_ANNOTATION)
    worker_cloudsql = worker.annotations.get(_CLOUDSQL_ANNOTATION)
    if api_cloudsql != worker_cloudsql:
        errors.append(
            "API/worker drift for Cloud SQL instance binding: "
            f"api={api_cloudsql or '<missing>'}, worker={worker_cloudsql or '<missing>'}."
        )

    min_scale = _first_annotation(worker.annotations, _MIN_SCALE_ANNOTATIONS)
    if min_scale != "1":
        errors.append(
            f"{worker.name}: expected minScale=1, found {min_scale or '<missing>'}."
        )

    max_scale = _first_annotation(worker.annotations, _MAX_SCALE_ANNOTATIONS)
    if max_scale != "1":
        errors.append(
            f"{worker.name}: expected maxScale=1, found {max_scale or '<missing>'}."
        )

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate platform-control API/worker runtime parity for worker-backed dispatch."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--region", default="europe-west6")
    parser.add_argument("--env", default="dev")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_name = f"platform-control-api-{args.env}"
    worker_name = f"platform-control-worker-{args.env}"
    try:
        api = describe_service(args.project_id, args.region, api_name)
        worker = describe_service(args.project_id, args.region, worker_name)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors = evaluate(api, worker)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        "Connector worker runtime check passed: "
        f"{api.name} and {worker.name} are aligned for worker-backed dispatch."
    )
    return 0


def _first_annotation(annotations: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = annotations.get(key)
        if value is not None:
            return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
