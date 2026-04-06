#!/usr/bin/env python3
"""Fail if staging smoke workflow references dev-scoped settings."""

from pathlib import Path
import sys


WORKFLOW_PATH = Path(".github/workflows/e2e-smoke-staging.yml")

DISALLOWED_SNIPPETS = (
    "GCP_PROJECT_ID_DEV",
    "GCP_SERVICE_ACCOUNT_DEV",
    "SMOKE_SEED_URL_DEV",
    "SMOKE_REQUEST_TIMEOUT_SECONDS_DEV",
    "DI_SURFACES_ROOT_URI_DEV",
    "E2E_SMOKE_DEV_SLACK_WEBHOOK",
    "_DEV",
)

REQUIRED_SNIPPETS = (
    "TARGET_ENV: staging",
    "environment: staging",
    "GCP_PROJECT_ID_STAGING",
    "GCP_SERVICE_ACCOUNT_STAGING",
    "DI_SURFACES_ROOT_URI_STAGING",
)


def main() -> int:
    if not WORKFLOW_PATH.exists():
        print(f"Missing workflow file: {WORKFLOW_PATH}", file=sys.stderr)
        return 1

    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    violations: list[str] = []
    for snippet in DISALLOWED_SNIPPETS:
        if snippet in content:
            violations.append(f"disallowed reference found: {snippet}")

    missing: list[str] = []
    for snippet in REQUIRED_SNIPPETS:
        if snippet not in content:
            missing.append(f"required staging reference missing: {snippet}")

    if violations or missing:
        print("Staging smoke workflow isolation check failed.", file=sys.stderr)
        for message in violations + missing:
            print(f"- {message}", file=sys.stderr)
        return 1

    print("Staging smoke workflow isolation check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
