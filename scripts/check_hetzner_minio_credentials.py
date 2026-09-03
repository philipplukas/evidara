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
5. Each policy's **actions and object prefix** must match the `access` (`ro`/`wo`/`rw`)
   and `prefix` its account declares. Bucket sets alone are not enough: adding
   `s3:PutObject` on `arn:aws:s3:::evidara-lakehouse/canonical/*` to the read-only
   `document-service` policy changes no bucket set, and would let a compromised read API
   corrupt the canonical surfaces legal-search indexes.
6. `accounts.json` must classify every bucket for every account (allow or deny), so a
   new bucket cannot be silently untested by `verify-minio-scoping.sh`.
7. No file under `infra/hetzner/apps/`, `infra/hetzner/values/` or
   `postgres-cluster.yaml` may reference the `minio-root` Secret, and any
   `evidara-s3-*` Secret they reference must be one `accounts.json` provisions.

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


# Bucket-level operations, granted for any allowed bucket whatever the `access`.
BUCKET_ACTIONS = frozenset(
    {"s3:ListBucket", "s3:GetBucketLocation", "s3:ListBucketMultipartUploads"}
)
# Object-level operations, gated on `access`. `wo` gets WRITE and NOT read; `ro` the
# reverse. This is the whole least-privilege claim, so it is checked, not asserted:
# checking bucket sets alone let `document-service` silently acquire s3:PutObject on
# the canonical surfaces it is supposed to be unable to touch.
READ_ACTIONS = frozenset({"s3:GetObject"})
WRITE_ACTIONS = frozenset(
    {
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts",
    }
)
ACCESS_OBJECT_ACTIONS = {
    "ro": READ_ACTIONS,
    "wo": WRITE_ACTIONS,
    "rw": READ_ACTIONS | WRITE_ACTIONS,
}


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    return [value]


def _policy_buckets(document: dict) -> tuple[set[str], set[str]]:
    """Return (buckets named, wildcard resources found) for one policy document."""
    buckets: set[str] = set()
    wildcards: set[str] = set()
    for statement in document.get("Statement") or []:
        for resource in _as_list(statement.get("Resource")):
            if not isinstance(resource, str) or resource in WILDCARD_RESOURCES:
                wildcards.add(str(resource))
                continue
            if not resource.startswith(_ARN_PREFIX):
                wildcards.add(resource)
                continue
            buckets.add(resource[len(_ARN_PREFIX) :].split("/", 1)[0])
    return buckets, wildcards


def _check_policy_actions(
    problems: list[str],
    policy: dict,
    policy_rel: object,
    user: str,
    allow_entries: dict[str, dict],
) -> None:
    """Assert each statement's actions and object prefix match the declared `access`.

    Bucket-set equality is not enough. Adding `s3:PutObject` on
    `arn:aws:s3:::evidara-lakehouse/canonical/*` to the read-only `document-service`
    policy changes no bucket set at all — and would let a compromised read API corrupt
    or delete the canonical surfaces legal-search indexes.
    """
    seen_buckets: set[str] = set()
    for statement in policy.get("Statement") or []:
        if statement.get("Effect") != "Allow":
            # A Deny only narrows; nothing to enforce.
            continue
        sid = statement.get("Sid", "<unnamed statement>")
        actions = {a for a in _as_list(statement.get("Action")) if isinstance(a, str)}
        for resource in _as_list(statement.get("Resource")):
            if not isinstance(resource, str) or not resource.startswith(_ARN_PREFIX):
                continue  # already reported as a wildcard by _policy_buckets
            remainder = resource[len(_ARN_PREFIX) :]
            bucket, _, key_pattern = remainder.partition("/")
            entry = allow_entries.get(bucket)
            if entry is None:
                continue  # already reported as an undeclared bucket
            seen_buckets.add(bucket)
            access = entry.get("access", "")
            prefix = entry.get("prefix", "")

            if "/" not in remainder:
                permitted = BUCKET_ACTIONS
                level = "bucket-level"
            else:
                permitted = ACCESS_OBJECT_ACTIONS.get(access, frozenset())
                level = f"object-level (access `{access}`)"
                expected_pattern = f"{prefix}*"
                if key_pattern != expected_pattern:
                    problems.append(
                        f"{policy_rel}: statement `{sid}` scopes objects to "
                        f"`{key_pattern}` but account `{user}` declares prefix "
                        f"`{prefix}` for {bucket} — the Resource must be exactly "
                        f"`{_ARN_PREFIX}{bucket}/{expected_pattern}` so the deny tests "
                        "probe inside the granted prefix (#813)"
                    )
                if not access:
                    problems.append(
                        f"{policy_rel}: account `{user}` declares no `access` for {bucket}"
                    )
            over = sorted(actions - permitted)
            if over:
                problems.append(
                    f"{policy_rel}: statement `{sid}` grants {over} at the {level} for "
                    f"{bucket}, which account `{user}` does not declare in accounts.json "
                    "— the policy is wider than the tested scope (#813)"
                )

    missing = sorted(set(allow_entries) - seen_buckets)
    if missing:
        problems.append(
            f"{policy_rel}: account `{user}` declares {missing} in `allow`, but the "
            "policy document grants nothing there"
        )


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
        allow_entries = {entry["bucket"]: entry for entry in account.get("allow") or []}
        allowed = set(allow_entries)
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

        _check_policy_actions(problems, policy, policy_rel, user, allow_entries)


# Deployment files that may name a Secret. `values/trino.yaml` is checked in more detail
# by check_trino, but it is walked here too so a NEW values file cannot slip root in.
def _manifest_paths() -> list[Path]:
    paths = sorted(HETZNER.glob("apps/*.yaml")) + sorted(HETZNER.glob("values/*.yaml"))
    cluster = HETZNER / "postgres-cluster.yaml"
    if cluster.is_file():
        paths.append(cluster)
    return paths


def _walk_secret_refs(node: object):
    """Yield every Secret name referenced by a `secretRef` / `secretKeyRef` anywhere."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"secretRef", "secretKeyRef"} and isinstance(value, dict):
                name = value.get("name")
                if isinstance(name, str):
                    yield name
            yield from _walk_secret_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_secret_refs(item)


def check_workload_manifests(problems: list[str], known_secrets: set[str]) -> None:
    """No workload manifest may name the administrative root Secret.

    Checking only `values/trino.yaml` and `deploy-stage4.sh` left the obvious hole:
    adding `- secretRef: {name: minio-root}` to `apps/platform-control.yaml` passed the
    guard clean while putting root back into a running pod.
    """
    for path in _manifest_paths():
        rel = path.relative_to(REPO_ROOT)
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as error:
            problems.append(f"{rel}: not valid YAML ({error})")
            continue
        for name in {n for doc in documents for n in _walk_secret_refs(doc)}:
            if name == ROOT_SECRET:
                problems.append(
                    f"{rel}: references the administrative `{ROOT_SECRET}` Secret. Every "
                    "workload gets its own scoped MinIO account — see "
                    "infra/hetzner/minio-policies/accounts.json (#813)"
                )
            elif name.startswith("evidara-s3-") and name not in known_secrets:
                problems.append(
                    f"{rel}: references `{name}`, which no account in "
                    "infra/hetzner/minio-policies/accounts.json provisions — nothing "
                    "would ever create it (#813)"
                )


def main() -> int:
    problems: list[str] = []
    for path in (MINIO_VALUES, TRINO_VALUES, STAGE4, ACCOUNTS_JSON):
        if not path.exists():
            print(f"FAIL: {path.relative_to(REPO_ROOT)} does not exist.")
            return 1

    try:
        known_secrets = {
            account.get("k8s_secret")
            for account in json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8")).get(
                "accounts", []
            )
        }
    except (OSError, json.JSONDecodeError):
        known_secrets = set()

    check_minio(problems)
    check_trino(problems)
    check_stage4(problems)
    check_policies(problems)
    check_workload_manifests(problems, known_secrets)

    if problems:
        print("FAIL: MinIO credentials are committed, or a workload still runs as root")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        "OK: Hetzner MinIO credentials are referenced not inlined, no workload or manifest "
        "uses root, and every policy's buckets, actions and prefixes match accounts.json"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
