#!/usr/bin/env python3
"""Guard the MinIO credential out of `infra/hetzner/values/{minio,trino}.yaml` (#792).

There is no cluster in CI, so this cannot prove MinIO runs. It proves the one thing
checkable from the files alone, and the one that already cost us a live credential:
**the root password is referenced, never inlined.**

#792 was not a near miss. `rootPassword: change-me-minio-root` sat on `main` from #504
and was the credential the cluster was actually running, granting full access to
`evidara-raw-artifacts` and `evidara-lakehouse` to anything with cluster access — which
includes the self-hosted CI runners sharing that node. Trino carried its own copy of the
same string in `s3.aws-secret-key`. Neither was caught, because nothing looked.

Two files, because the credential had two homes and fixing only the obvious one leaves
the leak in place:

1. `values/minio.yaml` must set `existingSecret` and must NOT set `rootPassword`
   (the chart prefers an inline value when both are present, so a re-added
   `rootPassword` silently wins over the Secret).
2. `values/trino.yaml` must reference its S3 credentials through `${ENV:...}`
   substitution, not literals.

Usage:
    python3 scripts/check_hetzner_minio_credentials.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MINIO_VALUES = REPO_ROOT / "infra" / "hetzner" / "values" / "minio.yaml"
TRINO_VALUES = REPO_ROOT / "infra" / "hetzner" / "values" / "trino.yaml"

# The credential that actually leaked. Present in comments describing the incident,
# so only a real assignment counts — `key: value`, not prose mentioning it.
LEAKED = "change-me-minio-root"
ASSIGNED_LEAK = re.compile(rf"^\s*[\w.-]+\s*[:=]\s*['\"]?{re.escape(LEAKED)}", re.MULTILINE)

# An S3 secret assigned a literal rather than an ${ENV:...} reference.
S3_SECRET_LITERAL = re.compile(
    r"^\s*s3\.aws-secret-key\s*=\s*(?!\$\{ENV:)(.+)$", re.MULTILINE
)
S3_ACCESS_LITERAL = re.compile(
    r"^\s*s3\.aws-access-key\s*=\s*(?!\$\{ENV:)(.+)$", re.MULTILINE
)


def check_minio(problems: list[str]) -> None:
    raw = MINIO_VALUES.read_text(encoding="utf-8")
    values = yaml.safe_load(raw) or {}

    if not values.get("existingSecret"):
        problems.append(
            f"{MINIO_VALUES.relative_to(REPO_ROOT)}: `existingSecret` is not set — the "
            "root credential must come from a pre-created Secret (README.md, Stage 1)"
        )
    # An empty string is the chart's own default and is fine; a real value is not.
    if values.get("rootPassword"):
        problems.append(
            f"{MINIO_VALUES.relative_to(REPO_ROOT)}: `rootPassword` is set inline. The "
            "chart prefers it over `existingSecret`, so this silently defeats the Secret"
        )
    if ASSIGNED_LEAK.search(raw):
        problems.append(
            f"{MINIO_VALUES.relative_to(REPO_ROOT)}: assigns the leaked #792 credential"
        )


def check_trino(problems: list[str]) -> None:
    raw = TRINO_VALUES.read_text(encoding="utf-8")
    values = yaml.safe_load(raw) or {}

    catalogs = values.get("catalogs") or {}
    for name, body in catalogs.items():
        if not isinstance(body, str):
            continue
        for pattern, key in (
            (S3_SECRET_LITERAL, "s3.aws-secret-key"),
            (S3_ACCESS_LITERAL, "s3.aws-access-key"),
        ):
            for match in pattern.finditer(body):
                problems.append(
                    f"{TRINO_VALUES.relative_to(REPO_ROOT)}: catalog `{name}` sets "
                    f"{key} to the literal `{match.group(1).strip()}` — use "
                    "${ENV:...} backed by a Secret (#792)"
                )

    if ASSIGNED_LEAK.search(raw):
        problems.append(
            f"{TRINO_VALUES.relative_to(REPO_ROOT)}: assigns the leaked #792 credential"
        )


def main() -> int:
    problems: list[str] = []
    for path in (MINIO_VALUES, TRINO_VALUES):
        if not path.exists():
            print(f"FAIL: {path.relative_to(REPO_ROOT)} does not exist.")
            return 1

    check_minio(problems)
    check_trino(problems)

    if problems:
        print("FAIL: MinIO credentials are committed to Hetzner values")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("OK: infra/hetzner/values/{minio,trino}.yaml reference credentials, not inline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
