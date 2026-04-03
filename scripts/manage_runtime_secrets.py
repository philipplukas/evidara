#!/usr/bin/env python3
"""Create and seed runtime secrets in Google Secret Manager.

This helper keeps the usual split:
- Upstream-provided values are entered manually.
- Internal secrets can be generated automatically when requested.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SecretSpec:
    base_name: str
    prompt: str
    source: str  # "upstream" | "internal"

    def secret_id(self, environment: str) -> str:
        return f"{self.base_name}-{environment}"


SECRET_SPECS: tuple[SecretSpec, ...] = (
    SecretSpec("opensearch-node", "OPENSEARCH_NODE", "upstream"),
    SecretSpec("opensearch-username", "OPENSEARCH_USERNAME", "upstream"),
    SecretSpec("opensearch-password", "OPENSEARCH_PASSWORD", "upstream"),
    SecretSpec("firecrawl-api-key", "FIRECRAWL_API_KEY", "upstream"),
    SecretSpec("firecrawl-webhook-secret", "FIRECRAWL_WEBHOOK_SECRET", "upstream"),
    SecretSpec("platform-control-database-url", "PLATFORM_CONTROL_DATABASE_URL", "upstream"),
)


def run_gcloud(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gcloud", *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def ensure_secret_exists(project_id: str, secret_id: str) -> None:
    describe = run_gcloud(["secrets", "describe", secret_id, f"--project={project_id}"])
    if describe.returncode == 0:
        return
    create = run_gcloud(
        [
            "secrets",
            "create",
            secret_id,
            "--replication-policy=automatic",
            f"--project={project_id}",
        ]
    )
    if create.returncode != 0:
        raise RuntimeError(
            f"Failed to create secret {secret_id}: {create.stderr.strip() or create.stdout.strip()}"
        )
    print(f"Created secret: {secret_id}")


def add_secret_version(project_id: str, secret_id: str, value: str) -> None:
    add = run_gcloud(
        [
            "secrets",
            "versions",
            "add",
            secret_id,
            "--data-file=-",
            f"--project={project_id}",
        ],
        input_text=value,
    )
    if add.returncode != 0:
        raise RuntimeError(
            f"Failed to add version for {secret_id}: {add.stderr.strip() or add.stdout.strip()}"
        )
    print(f"Added secret version: {secret_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and seed runtime secrets for an environment.")
    parser.add_argument("--project-id", required=True, help="GCP project id")
    parser.add_argument("--env", default="dev", help="Environment suffix (dev/staging/prod)")
    parser.add_argument(
        "--generate-internal",
        action="store_true",
        help="Auto-generate values for internal secret specs.",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="Optional base secret names to process (example: firecrawl-api-key opensearch-node).",
    )
    parser.add_argument(
        "--from-env-file",
        default=None,
        help=(
            "Optional .env file path. If a matching ENV key exists, that value is used "
            "instead of interactive prompt."
        ),
    )
    return parser.parse_args()


def select_specs(only: list[str]) -> list[SecretSpec]:
    if not only:
        return list(SECRET_SPECS)
    allowed = set(only)
    selected = [spec for spec in SECRET_SPECS if spec.base_name in allowed]
    missing = sorted(allowed - {spec.base_name for spec in selected})
    if missing:
        raise ValueError(f"Unknown secret name(s): {', '.join(missing)}")
    return selected


def resolve_value(spec: SecretSpec, generate_internal: bool) -> str | None:
    if spec.source == "internal" and generate_internal:
        return secrets.token_urlsafe(48)
    value = getpass.getpass(f"Enter {spec.prompt} (leave blank to skip): ").strip()
    return value or None


def load_env_file(env_file: str | None) -> dict[str, str]:
    if not env_file:
        return {}
    path = Path(env_file)
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {env_file}")
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        parsed[key] = value
    return parsed


def main() -> int:
    args = parse_args()
    try:
        specs = select_specs(args.only)
        env_values = load_env_file(args.from_env_file)
        print(
            "Processing secrets for project "
            f"{args.project_id} ({args.env}) - {len(specs)} item(s)."
        )
        if args.from_env_file:
            print(f"Using env file values from: {args.from_env_file}")
        for spec in specs:
            secret_id = spec.secret_id(args.env)
            ensure_secret_exists(args.project_id, secret_id)
            value = env_values.get(spec.prompt)
            if value:
                print(f"Using value from env file for: {spec.prompt}")
            else:
                value = resolve_value(spec, args.generate_internal)
            if value is None:
                print(f"Skipped value update: {secret_id}")
                continue
            add_secret_version(args.project_id, secret_id, value)
        print("Done.")
        return 0
    except Exception as exc:  # pragma: no cover - operational script
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
