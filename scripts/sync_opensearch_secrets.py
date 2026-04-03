#!/usr/bin/env python3
"""Sync OpenSearch Terraform outputs into GCP Secret Manager.

Expected Terraform outputs in the OpenSearch stack:
- service_uri
- service_username
- service_password
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str], *, cwd: str | None = None, input_text: str | None = None) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{stderr}")
    return result.stdout


def terraform_outputs_json(stack_dir: Path) -> dict:
    raw = run_cmd(["terraform", "output", "-json"], cwd=str(stack_dir))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid terraform output JSON: {exc}") from exc


def read_output(outputs: dict, key: str, *, allow_empty: bool = False) -> str:
    if key not in outputs:
        raise RuntimeError(f"Missing terraform output: {key}")
    value = outputs[key].get("value")
    if (value is None or value == "") and not allow_empty:
        raise RuntimeError(f"Terraform output is empty: {key}")
    return "" if value is None else str(value)


def ensure_secret_exists(project_id: str, secret_id: str) -> None:
    describe = subprocess.run(
        ["gcloud", "secrets", "describe", secret_id, f"--project={project_id}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if describe.returncode == 0:
        return
    run_cmd(
        [
            "gcloud",
            "secrets",
            "create",
            secret_id,
            "--replication-policy=automatic",
            f"--project={project_id}",
        ]
    )
    print(f"Created secret: {secret_id}")


def add_secret_version(project_id: str, secret_id: str, value: str) -> None:
    run_cmd(
        [
            "gcloud",
            "secrets",
            "versions",
            "add",
            secret_id,
            "--data-file=-",
            f"--project={project_id}",
        ],
        input_text=value,
    )
    print(f"Added secret version: {secret_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync OpenSearch Terraform outputs into GCP Secret Manager."
    )
    parser.add_argument("--project-id", required=True, help="Target GCP project id")
    parser.add_argument("--env", default="dev", help="Environment suffix (dev/staging/prod)")
    parser.add_argument(
        "--opensearch-stack-dir",
        default="infra/terraform/opensearch/gke_stack",
        help="Path to Terraform OpenSearch stack directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended secret updates without writing versions.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        stack_dir = Path(args.opensearch_stack_dir)
        if not stack_dir.exists():
            raise FileNotFoundError(f"Stack directory not found: {stack_dir}")

        outputs = terraform_outputs_json(stack_dir)
        if not outputs:
            raise RuntimeError(
                "No terraform outputs found. Apply the OpenSearch stack first "
                "(terraform apply in infra/terraform/opensearch/gke_stack)."
            )
        node = read_output(outputs, "service_uri", allow_empty=True)
        if not node:
            host = read_output(outputs, "service_host")
            port = read_output(outputs, "service_port")
            node = f"https://{host}:{port}"
        username = read_output(outputs, "service_username")
        password = read_output(outputs, "service_password")

        mappings = {
            f"opensearch-node-{args.env}": node,
            f"opensearch-username-{args.env}": username,
            f"opensearch-password-{args.env}": password,
        }

        print("Resolved OpenSearch outputs:")
        print(f"- service_uri: {node}")
        print(f"- service_username: {username}")
        print("- service_password: <redacted>")

        if args.dry_run:
            print("\nDry run mode. Would update secret versions:")
            for secret_id in mappings:
                print(f"- {secret_id}")
            return 0

        for secret_id, value in mappings.items():
            ensure_secret_exists(args.project_id, secret_id)
            add_secret_version(args.project_id, secret_id, value)

        print("Done.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
