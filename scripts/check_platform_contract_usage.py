#!/usr/bin/env python3
"""Assert this repo only uses platform resources the contract declares.

WHY. Evidara's manifests reference the platform by string: an S3 Secret name, an
ingress class, a ClusterIssuer. Nothing checked those strings against anything,
which is how the estate acquired dependencies nobody declared — `mlops-api-tls`
issued by a ClusterIssuer defined in a different repository, and a 36-day outage
from an Ingress annotated with the *staging* issuer, a failure whose only symptom
is an untrusted certificate.

The platform layer moved to research-platform on 2026-09-07, so the strings now
cross a repository boundary and cannot be checked by reading this repo alone.
`vendor/platform-contract.yaml` is the pinned copy that makes it possible.

WHAT THIS DELIBERATELY DOES NOT DO. It does not validate the platform's own MinIO
policies, Zitadel values or issuers — those live upstream and are checked there.
`check_hetzner_minio_credentials.py` and `check_hetzner_zitadel.py` still read
frozen copies under infra/hetzner/, which are duplicates awaiting deletion; see
infra/hetzner/OWNERSHIP.md. This check reads only the contract, so it keeps
working after those copies are gone.

    python3 scripts/check_platform_contract_usage.py
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

CONTRACT = pathlib.Path("vendor/platform-contract.yaml")
# Only surfaces this repository owns. The platform's own manifests are upstream.
SEARCH = [
    pathlib.Path("infra/hetzner/apps"),
    pathlib.Path("infra/hetzner/auth/ingress-tls.yaml"),
    pathlib.Path("infra/hetzner/marketing"),
    pathlib.Path("infra/hetzner/observability"),
    pathlib.Path("infra/hetzner/postgres-cluster.yaml"),
]

S3_SECRET = re.compile(r"\b(evidara-s3-[a-z0-9-]+|cnpg-minio-backup)\b")
ISSUER_ANNOTATION = re.compile(r"cert-manager\.io/cluster-issuer:\s*[\"']?([A-Za-z0-9._-]+)")
INGRESS_CLASS = re.compile(r"ingressClassName:\s*[\"']?([A-Za-z0-9._-]+)")


def files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for p in SEARCH:
        if p.is_dir():
            out += sorted(p.rglob("*.yaml"))
        elif p.is_file():
            out.append(p)
    return out


def main() -> int:
    if not CONTRACT.is_file():
        print(f"missing {CONTRACT} — see the platform contract section in README.md")
        return 1
    c = yaml.safe_load(CONTRACT.read_text())

    allowed_secrets = {a["secret"] for a in c["s3"]["accounts"].values()}
    allowed_issuers = set(c["ingress"]["issuers"].values())
    allowed_classes = set(c["ingress"]["classes"].values())

    problems: list[str] = []
    for f in files():
        text = f.read_text()
        for m in sorted(set(S3_SECRET.findall(text))):
            if m not in allowed_secrets:
                problems.append(f"{f}: S3 Secret {m!r} is not in the contract")
        for m in sorted(set(ISSUER_ANNOTATION.findall(text))):
            if m not in allowed_issuers:
                problems.append(f"{f}: ClusterIssuer {m!r} is not in the contract")
        for m in sorted(set(INGRESS_CLASS.findall(text))):
            if m not in allowed_classes:
                problems.append(f"{f}: ingressClassName {m!r} is not in the contract")

    if problems:
        print("Platform resources used here but not declared by the contract:\n")
        for p in problems:
            print(f"  {p}")
        print(
            f"\nContract: {CONTRACT} (pinned {c['contractVersion']}), from research-platform."
            "\n\nEither the name is wrong — which in the cluster shows up as a Pod that will"
            "\nnot start, or a certificate nobody trusts — or the platform gained something"
            "\nthis pin predates, in which case refresh the vendored copy and the README pin."
        )
        return 1

    n = len(files())
    print(
        f"✅ {n} manifests use only contract-declared platform resources "
        f"({len(allowed_secrets)} S3 Secrets, {len(allowed_issuers)} issuers, "
        f"{len(allowed_classes)} ingress classes; contract {c['contractVersion']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
