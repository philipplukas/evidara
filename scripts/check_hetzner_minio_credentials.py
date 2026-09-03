#!/usr/bin/env python3
"""Guard the MinIO credential out of the Hetzner deployment files (#792, #813).

There is no cluster in CI, so this cannot prove MinIO runs. It proves the things
checkable from the files alone, and they are the two that already cost us something:
**the root password is referenced, never inlined** (#792), and **no workload
authenticates as root at all** (#813).

#792 was not a near miss. `rootPassword: change-me-minio-root` sat on `main` from #504
and was the credential the cluster was actually running, granting full access to
`evidara-raw-artifacts` and `evidara-lakehouse` to anything with cluster access — which
includes the self-hosted CI runners sharing that node. Trino carried its own copy of the
same string in `s3.aws-secret-key`. Neither was caught, because nothing looked.

#813 is the half #792 deliberately left: the credential stopped being *committed*, but
`platform-control-api`, `di-consumer`, `document-service`, `projection-bridge` and both
Trino pods still authenticated as **root**, so a compromise of any one of them reached
the raw artifacts, the lakehouse *and* the `evidara-pg-backups` PITR backups that exist
to recover from exactly that.

What is checked:

1. `values/minio.yaml` must set `existingSecret` and must NOT set `rootPassword`
   (the chart prefers an inline value when both are present, so a re-added
   `rootPassword` silently wins over the Secret).
2. `values/trino.yaml` must reference its S3 credentials through `${ENV:...}`
   substitution, not literals, and those env vars must come from a scoped Secret —
   **not** `minio-root`.
3. `deploy-stage4.sh` must not read `minio-root` and must not seed any `*_S3_*`
   credential into the shared `evidara-app-secrets` Secret: it is mounted with
   `envFrom` by every app, so anything in it is held by all of them.
4. Every policy document in `infra/hetzner/minio-policies/` must name concrete bucket
   ARNs — a `Resource: "*"` or `arn:aws:s3:::*` grant is root by another name — and
   every bucket a policy names must be one of `accounts.json`'s `all_buckets`.
5. `accounts.json` must classify every bucket for every account (allow or deny), so a
   new bucket cannot be silently untested by `verify-minio-scoping.sh`.

Usage:
    python3 scripts/check_hetzner_minio_credentials.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HETZNER = REPO_ROOT / "infra" / "hetzner"
MINIO_VALUES = HETZNER / "values" / "minio.yaml"
TRINO_VALUES = HETZNER / "values" / "trino.yaml"
STAGE4 = HETZNER / "deploy-stage4.sh"
POLICY_DIR = HETZNER / "minio-policies"
ACCOUNTS_JSON = POLICY_DIR / "accounts.json"

# The Secret holding the administrative root credential. Referencing it from a workload
# is the #813 defect, whatever the file.
ROOT_SECRET = "minio-root"

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

    for entry in values.get("env") or []:
        if not isinstance(entry, dict):
            continue
        ref = ((entry.get("valueFrom") or {}).get("secretKeyRef") or {}).get("name")
        if ref == ROOT_SECRET:
            problems.append(
                f"{TRINO_VALUES.relative_to(REPO_ROOT)}: env `{entry.get('name')}` reads "
                f"the administrative `{ROOT_SECRET}` Secret. Trino needs "
                "`evidara-lakehouse` only — use its scoped `evidara-s3-trino` Secret (#813)"
            )


# `deploy-stage4.sh` builds `evidara-app-secrets`, which every app mounts with envFrom.
# An S3 credential in it is held by every workload at once — including `projection-bridge`,
# which makes no object-storage call at all.
STAGE4_READS_ROOT = re.compile(rf"get\s+secret\s+{re.escape(ROOT_SECRET)}\b")
STAGE4_SEEDS_S3 = re.compile(r"--from-literal=([A-Z_]*S3_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY))")


def check_stage4(problems: list[str]) -> None:
    raw = STAGE4.read_text(encoding="utf-8")
    rel = STAGE4.relative_to(REPO_ROOT)
    if STAGE4_READS_ROOT.search(raw):
        problems.append(
            f"{rel}: reads the administrative `{ROOT_SECRET}` Secret. The app deploy must "
            "not touch root — per-workload credentials come from provision-minio-users.sh (#813)"
        )
    for match in STAGE4_SEEDS_S3.finditer(raw):
        problems.append(
            f"{rel}: seeds `{match.group(1)}` into a Secret every app mounts with envFrom. "
            "Object-storage credentials belong in per-workload `evidara-s3-*` Secrets (#813)"
        )


WILDCARD_RESOURCES = {"*", "arn:aws:s3:::*", "arn:aws:s3:::*/*"}
_ARN_PREFIX = "arn:aws:s3:::"


def _policy_buckets(document: dict) -> tuple[set[str], set[str]]:
    """Return (buckets named, wildcard resources found) for one policy document."""
    buckets: set[str] = set()
    wildcards: set[str] = set()
    for statement in document.get("Statement") or []:
        resources = statement.get("Resource")
        if isinstance(resources, str):
            resources = [resources]
        for resource in resources or []:
            if resource in WILDCARD_RESOURCES:
                wildcards.add(resource)
                continue
            if not resource.startswith(_ARN_PREFIX):
                wildcards.add(resource)
                continue
            buckets.add(resource[len(_ARN_PREFIX) :].split("/", 1)[0])
    return buckets, wildcards


def check_policies(problems: list[str]) -> None:
    accounts_rel = ACCOUNTS_JSON.relative_to(REPO_ROOT)
    try:
        accounts_doc = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        problems.append(f"{accounts_rel}: unreadable ({error})")
        return

    all_buckets = set(accounts_doc.get("all_buckets") or [])
    if not all_buckets:
        problems.append(f"{accounts_rel}: `all_buckets` is empty")
        return

    for account in accounts_doc.get("accounts") or []:
        user = account.get("user", "<unnamed>")
        allowed = {entry["bucket"] for entry in account.get("allow") or []}
        denied = set(account.get("deny") or [])
        unclassified = sorted(all_buckets - allowed - denied)
        if unclassified:
            problems.append(
                f"{accounts_rel}: account `{user}` classifies neither allow nor deny for "
                f"{unclassified} — verify-minio-scoping.sh would never test it (#813)"
            )
        overlap = sorted(allowed & denied)
        if overlap:
            problems.append(
                f"{accounts_rel}: account `{user}` lists {overlap} as both allowed and denied"
            )

        policy_path = POLICY_DIR / account.get("policy_file", "")
        if not policy_path.is_file():
            problems.append(f"{accounts_rel}: account `{user}` names a missing policy document")
            continue
        policy_rel = policy_path.relative_to(REPO_ROOT)
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            problems.append(f"{policy_rel}: not valid JSON ({error})")
            continue

        buckets, wildcards = _policy_buckets(policy)
        for wildcard in sorted(wildcards):
            problems.append(
                f"{policy_rel}: grants `{wildcard}` — an all-buckets grant is root by "
                "another name, which is the whole of #813"
            )
        unknown = sorted(buckets - all_buckets)
        if unknown:
            problems.append(
                f"{policy_rel}: names bucket(s) {unknown} that are not in "
                f"{accounts_rel}'s `all_buckets`"
            )
        extra = sorted(buckets - allowed)
        if extra:
            problems.append(
                f"{policy_rel}: grants access to {extra}, which account `{user}` does not "
                "declare in `allow` — the policy is wider than the tested scope (#813)"
            )


def main() -> int:
    problems: list[str] = []
    for path in (MINIO_VALUES, TRINO_VALUES, STAGE4, ACCOUNTS_JSON):
        if not path.exists():
            print(f"FAIL: {path.relative_to(REPO_ROOT)} does not exist.")
            return 1

    check_minio(problems)
    check_trino(problems)
    check_stage4(problems)
    check_policies(problems)

    if problems:
        print("FAIL: MinIO credentials are committed, or a workload still runs as root")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        "OK: Hetzner MinIO credentials are referenced not inlined, no workload uses root, "
        "and every policy is scoped to declared buckets"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
