#!/usr/bin/env python3
"""Derive the MinIO scoping assertions from accounts.json (#813).

Extracted from `verify-minio-scoping.sh` so it can be unit-tested. It used to be a
heredoc inside the script, and while it was, nothing checked that the assertions it
emits are capable of failing — which is how every `read` deny assertion came to be
vacuous: they were emitted against a key that does not exist, and a missing object
returns NoSuchKey whether or not `s3:GetObject` is granted.

Two outputs, both consumed by `verify-minio-scoping.sh`:

``--seeds``
    ``bucket:key`` pairs, deduplicated. Root writes one probe object at each before the
    account tests run, and removes them afterwards, so a denied read is a *permission*
    result rather than an absence.

``--matrix``
    One tab-separated line per account:
    ``user \\t k8s_secret \\t access_key_field \\t secret_key_field \\t checks``
    where ``checks`` is a space-separated list of ``bucket:check:expect:key``.

Expectations follow `access` exactly:

===========  ====  ====  =====
access       list  read  write
===========  ====  ====  =====
``ro``       allow allow deny
``wo``       allow deny  allow
``rw``       allow allow allow
(denied)     deny  deny  deny
===========  ====  ====  =====

Probe keys are always built from the account's declared ``prefix``, so a write probe can
never land outside the granted prefix and pass because of where it landed rather than
because of the policy.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

READ_PROBE = ".evidara-read-probe"
WRITE_PROBE = ".evidara-write-probe"

# (list, read, write) expectation per access level.
ACCESS_EXPECTATIONS = {
    "ro": ("allow", "allow", "deny"),
    "wo": ("allow", "deny", "allow"),
    "rw": ("allow", "allow", "allow"),
}
DENIED_EXPECTATIONS = ("deny", "deny", "deny")


class MatrixError(Exception):
    """accounts.json does not describe a testable matrix."""


def _probe_keys(prefix: str) -> tuple[str, str]:
    return f"{prefix}{READ_PROBE}", f"{prefix}{WRITE_PROBE}"


def build(document: dict) -> tuple[list[tuple[str, str]], list[dict]]:
    """Return (seeds, accounts) for one parsed accounts.json."""
    buckets = list(document.get("all_buckets") or [])
    if not buckets:
        raise MatrixError("accounts.json: `all_buckets` is empty")

    seeds: list[tuple[str, str]] = []
    seen_seeds: set[tuple[str, str]] = set()
    accounts: list[dict] = []

    for account in document.get("accounts") or []:
        user = account["user"]
        allowed = {entry["bucket"]: entry for entry in account.get("allow") or []}
        denied = set(account.get("deny") or [])
        unclassified = sorted(set(buckets) - set(allowed) - denied)
        if unclassified:
            raise MatrixError(
                f"accounts.json: account {user} does not classify {unclassified} "
                "— every bucket must be in `allow` or `deny`, or it goes untested"
            )
        overlap = sorted(set(allowed) & denied)
        if overlap:
            raise MatrixError(
                f"accounts.json: account {user} lists {overlap} as both allowed and denied"
            )

        checks: list[str] = []
        for bucket in buckets:
            entry = allowed.get(bucket)
            if entry is None:
                prefix = ""
                list_x, read_x, write_x = DENIED_EXPECTATIONS
            else:
                access = entry.get("access")
                if access not in ACCESS_EXPECTATIONS:
                    raise MatrixError(
                        f"accounts.json: account {user} declares unknown access "
                        f"{access!r} for {bucket} (expected ro/wo/rw)"
                    )
                prefix = entry.get("prefix", "")
                list_x, read_x, write_x = ACCESS_EXPECTATIONS[access]

            read_key, write_key = _probe_keys(prefix)
            checks.append(f"{bucket}:list:{list_x}:-")
            checks.append(f"{bucket}:read:{read_x}:{read_key}")
            checks.append(f"{bucket}:write:{write_x}:{write_key}")

            # Every read assertion — allow or deny — needs a real object behind it.
            seed = (bucket, read_key)
            if seed not in seen_seeds:
                seen_seeds.add(seed)
                seeds.append(seed)

        accounts.append(
            {
                "user": user,
                "k8s_secret": account["k8s_secret"],
                "access_key_field": account["access_key_field"],
                "secret_key_field": account["secret_key_field"],
                "checks": checks,
            }
        )

    return seeds, accounts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--seeds", action="store_true", help="emit `bucket:key` probe seeds")
    mode.add_argument("--matrix", action="store_true", help="emit the per-account TSV")
    mode.add_argument("--buckets", action="store_true", help="emit every bucket name")
    mode.add_argument(
        "--provision",
        action="store_true",
        help="emit the provisioning TSV: user, policy file, Secret, key fields",
    )
    parser.add_argument("accounts", type=Path)
    args = parser.parse_args(argv)

    try:
        document = json.loads(args.accounts.read_text(encoding="utf-8"))
        # `build` runs even for --provision and --buckets so that provisioning refuses to
        # create an account `verify-minio-scoping.sh` would not be able to test.
        seeds, accounts = build(document)
    except (OSError, json.JSONDecodeError, KeyError, MatrixError) as error:
        print(f"{args.accounts}: {error}", file=sys.stderr)
        return 1

    if args.buckets:
        print(" ".join(document["all_buckets"]))
        return 0

    if args.provision:
        for account in document["accounts"]:
            print(
                "\t".join(
                    (
                        account["user"],
                        account["policy_file"],
                        account["k8s_secret"],
                        account["access_key_field"],
                        account["secret_key_field"],
                    )
                )
            )
        return 0

    if args.seeds:
        print(" ".join(f"{bucket}:{key}" for bucket, key in seeds))
        return 0

    for account in accounts:
        print(
            "\t".join(
                (
                    account["user"],
                    account["k8s_secret"],
                    account["access_key_field"],
                    account["secret_key_field"],
                    " ".join(account["checks"]),
                )
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
