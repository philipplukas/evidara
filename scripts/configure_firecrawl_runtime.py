#!/usr/bin/env python3
"""Prepare Firecrawl runtime configuration from deployed GCP resources.

Firecrawl currently does not expose a Terraform provider for account-level settings.
This script automates the parts we can control:
- derive platform-control webhook URL from Cloud Run service URL
- optionally write webhook URL into runtime tfvars env_vars blocks
- print exact values to set in Firecrawl dashboard
"""

from __future__ import annotations

import argparse
import hmac
import json
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from urllib import request


def run_cmd(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{stderr}")
    return result.stdout.strip()


def cloud_run_url(project_id: str, region: str, env: str) -> str:
    service_name = f"platform-control-api-{env}"
    return run_cmd(
        [
            "gcloud",
            "run",
            "services",
            "describe",
            service_name,
            f"--region={region}",
            f"--project={project_id}",
            "--format=value(status.url)",
        ]
    )


def latest_secret_value(project_id: str, secret_id: str) -> str:
    return run_cmd(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={secret_id}",
            f"--project={project_id}",
        ]
    )


def update_tfvars_webhook_url(tfvars_path: Path, webhook_url: str) -> bool:
    text = tfvars_path.read_text(encoding="utf-8")
    key = "PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_URL"
    replacement_line = f'      {key} = "{webhook_url}"'

    if key in text:
        updated = re.sub(
            rf'^\s*{key}\s*=\s*".*?"\s*$',
            replacement_line,
            text,
            flags=re.MULTILINE,
        )
        if updated == text:
            return False
        tfvars_path.write_text(updated, encoding="utf-8")
        return True

    lines = text.splitlines()
    for service_name in ("platform-control-api", "platform-control-worker"):
        service_idx = _find_line_index(lines, f'  "{service_name}" = {{')
        if service_idx is None:
            continue
        env_vars_idx = _find_line_index(lines, "    env_vars = {", start=service_idx)
        if env_vars_idx is None:
            continue
        insert_idx = env_vars_idx + 1
        while insert_idx < len(lines) and lines[insert_idx].strip() != "}":
            insert_idx += 1
        lines.insert(insert_idx, replacement_line)
    updated_text = "\n".join(lines) + "\n"
    if updated_text == text:
        return False
    tfvars_path.write_text(updated_text, encoding="utf-8")
    return True


def _find_line_index(lines: list[str], needle: str, start: int = 0) -> int | None:
    for idx in range(start, len(lines)):
        if lines[idx] == needle:
            return idx
    return None


def verify_signed_callback(webhook_url: str, secret_value: str) -> int:
    payload = {"id": "setup-test", "type": "crawl.started", "data": []}
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret_value.encode("utf-8"), raw_body, digestmod=sha256).hexdigest()
    identity_token = run_cmd(["gcloud", "auth", "print-identity-token"])
    req = request.Request(
        webhook_url,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Firecrawl-Signature": f"sha256={signature}",
            "Authorization": f"Bearer {identity_token}",
        },
    )
    with request.urlopen(req, timeout=15) as response:
        return response.status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Firecrawl webhook runtime config for platform-control."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--region", default="europe-west6")
    parser.add_argument("--env", default="dev")
    parser.add_argument(
        "--tfvars-path",
        default=None,
        help="Optional path to runtime.gcp.tfvars to patch webhook URL into env_vars.",
    )
    parser.add_argument(
        "--verify-callback",
        action="store_true",
        help="Send a signed test callback to the webhook endpoint.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        base_url = cloud_run_url(args.project_id, args.region, args.env)
        if not base_url:
            raise RuntimeError("platform-control Cloud Run URL not found.")
        webhook_url = f"{base_url.rstrip('/')}/v1/firecrawl/webhooks"
        secret_id = f"firecrawl-webhook-secret-{args.env}"

        print("Derived runtime values:")
        print(f"- platform_control_api_url: {base_url}")
        print(f"- firecrawl_webhook_url: {webhook_url}")
        print(f"- webhook_secret_id: {secret_id}")

        if args.tfvars_path:
            tfvars_path = Path(args.tfvars_path)
            if not tfvars_path.exists():
                raise FileNotFoundError(f"tfvars file not found: {tfvars_path}")
            changed = update_tfvars_webhook_url(tfvars_path, webhook_url)
            print(f"- tfvars_updated: {'yes' if changed else 'no (already set)'}")

        print("\nFirecrawl dashboard settings to apply:")
        print("- Webhook URL: use firecrawl_webhook_url above")
        print("- Webhook secret: must match latest value in Secret Manager")
        print("  (Firecrawl app settings > Advanced)")

        if args.verify_callback:
            secret_value = latest_secret_value(args.project_id, secret_id)
            status = verify_signed_callback(webhook_url, secret_value)
            print(f"\nSigned callback verification status: HTTP {status}")

        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
