#!/usr/bin/env python3
"""Guard `infra/hetzner/values/zitadel.yaml` — the Zitadel deployment (ADR-0038 step 2).

There is no cluster in CI, so this cannot prove Zitadel runs. It proves the four
things that are checkable from the file alone and that would each be a silent,
expensive defect:

1. **No credential is committed.** #792 was exactly this failure in
   `values/minio.yaml` (`change-me-minio-root`, live on `main` until it was rotated;
   `scripts/check_hetzner_minio_credentials.py` now guards that pair). An IdP values
   file is the worst possible place to repeat it. Both of Zitadel's secrets — the
   database DSN and the masterkey — must be *references* to Secrets created
   out-of-band by `deploy-stage8.sh`.
2. **The bundled Postgres subchart stays off.** `postgresql.enabled: true` would
   spin up a second, unbacked-up Postgres holding every user credential, while
   the cluster still looked healthy. It defaults to `false`; this asserts nobody
   flipped it.
3. **The ingress matches the repo's cert-manager pattern.** `ingressClassName:
   traefik` plus the `letsencrypt-prod` ClusterIssuer from
   `infra/hetzner/auth/letsencrypt-issuer.yaml`. A typo'd issuer name yields an
   Ingress that serves the Traefik default self-signed cert — which looks like a
   working deployment until a browser refuses the OIDC redirect.
4. **`ExternalDomain` equals the ingress host.** Zitadel bakes `ExternalDomain`
   into the OIDC issuer URL and every redirect URI. If it disagrees with the host
   the ingress actually answers on, discovery succeeds, login starts, and the
   redirect back lands nowhere. This is the single most common self-hosted-Zitadel
   misconfiguration and nothing else in the pipeline would catch it.

Optionally (`--render`, or automatically when `helm` is on PATH and the chart is
already fetched) also renders the chart with these values so the chart's own
values schema gets a vote. Never required: the four checks above are the point.

Usage:
    python3 scripts/check_hetzner_zitadel.py
    python3 scripts/check_hetzner_zitadel.py --render
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
VALUES = REPO_ROOT / "infra" / "hetzner" / "values" / "zitadel.yaml"
ISSUER_MANIFEST = REPO_ROOT / "infra" / "hetzner" / "auth" / "letsencrypt-issuer.yaml"

CHART = "zitadel/zitadel"
CHART_VERSION = "10.0.4"
ISSUER_ANNOTATION = "cert-manager.io/cluster-issuer"

# Keys whose presence means a credential was inlined instead of referenced.
FORBIDDEN_INLINE_KEYS = {
    "masterkey": "zitadel.masterkey — use zitadel.masterkeySecretName instead",
    "password": "an inline password",
    "postgrespassword": "an inline Postgres superuser password",
    "dsn": "an inline database DSN (it carries the password)",
    "secretconfig": "zitadel.secretConfig writes credentials into the chart's values",
}

# A DSN with a password in it, wherever it appears.
DSN_WITH_PASSWORD = re.compile(r"postgres(?:ql)?://[^\s:/]+:[^\s@]+@", re.IGNORECASE)


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def walk(node: object, path: str = ""):
    """Yield (dotted_path, key, value) for every mapping entry in the tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield child, str(key), value
            yield from walk(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = f"{path}[{index}]"
            yield from walk(value, child)


def check_no_committed_credentials(values: dict, raw: str, problems: list[str]) -> None:
    for dotted, key, value in walk(values):
        lowered = key.lower()
        if lowered in FORBIDDEN_INLINE_KEYS and value not in (None, "", {}, []):
            fail(
                problems,
                f"{dotted}: {FORBIDDEN_INLINE_KEYS[lowered]} — no credential may be "
                f"committed to this file (#792). Create a Secret in "
                f"deploy-stage8.sh and reference it by name.",
            )
    if DSN_WITH_PASSWORD.search(raw):
        fail(
            problems,
            "a Postgres connection string with an embedded password appears in the "
            "file. The DSN belongs in the `zitadel-db` Secret, injected via "
            "`envVarsSecret`.",
        )
    if not values.get("zitadel", {}).get("masterkeySecretName"):
        fail(
            problems,
            "zitadel.masterkeySecretName is unset. Without it the chart wants an "
            "inline `zitadel.masterkey`, which is a committed credential.",
        )
    if not values.get("envVarsSecret"):
        fail(
            problems,
            "envVarsSecret is unset, so nothing supplies "
            "ZITADEL_DATABASE_POSTGRES_DSN. Zitadel would fall back to "
            "localhost/postgres defaults and the init job would fail.",
        )


def check_bundled_postgres_off(values: dict, problems: list[str]) -> None:
    if values.get("postgresql", {}).get("enabled"):
        fail(
            problems,
            "postgresql.enabled is true. That deploys a SECOND Postgres, outside "
            "the CNPG cluster and outside its backups, holding every user "
            "credential — the opposite of ADR-0038 §2's reason for choosing "
            "Zitadel. It must stay false.",
        )


def _known_cluster_issuers() -> set[str]:
    if not ISSUER_MANIFEST.exists():
        return set()
    names = set()
    for doc in yaml.safe_load_all(ISSUER_MANIFEST.read_text(encoding="utf-8")):
        if isinstance(doc, dict) and doc.get("kind") == "ClusterIssuer":
            name = doc.get("metadata", {}).get("name")
            if name:
                names.add(name)
    return names


def _ingress_blocks(values: dict) -> list[tuple[str, dict]]:
    blocks = []
    top = values.get("ingress")
    if isinstance(top, dict):
        blocks.append(("ingress", top))
    login = values.get("login", {}).get("ingress")
    if isinstance(login, dict):
        blocks.append(("login.ingress", login))
    return blocks


def check_ingress(values: dict, problems: list[str]) -> None:
    issuers = _known_cluster_issuers()
    blocks = [(name, block) for name, block in _ingress_blocks(values) if block.get("enabled")]
    if not blocks:
        fail(problems, "no ingress is enabled — Zitadel would be unreachable.")
        return

    annotated = 0
    for name, block in blocks:
        if block.get("className") != "traefik":
            fail(
                problems,
                f"{name}.className is {block.get('className')!r}; the cluster's "
                f"ingress controller is k3s' built-in traefik "
                f"(see infra/hetzner/auth/ingress-tls.yaml).",
            )
        if not block.get("tls"):
            fail(
                problems,
                f"{name} has no `tls:` block. A Traefik ingress without one gets an "
                f"HTTP-only router and never answers on 443.",
            )
        issuer = (block.get("annotations") or {}).get(ISSUER_ANNOTATION)
        if issuer is None:
            continue
        annotated += 1
        if issuers and issuer not in issuers:
            fail(
                problems,
                f"{name} references ClusterIssuer {issuer!r}, which is not defined "
                f"in {ISSUER_MANIFEST.relative_to(REPO_ROOT)} "
                f"(have: {', '.join(sorted(issuers))}).",
            )
    if annotated == 0:
        fail(
            problems,
            f"no enabled ingress carries the {ISSUER_ANNOTATION} annotation, so "
            f"cert-manager issues nothing and Traefik serves its default "
            f"self-signed cert.",
        )
    # Both ingresses share one TLS secret. Two cert-manager annotations pointing at
    # the same secretName make two Ingresses contend for one Certificate object.
    secrets = {
        entry.get("secretName")
        for _, block in blocks
        for entry in (block.get("tls") or [])
    }
    if annotated > 1 and len(secrets) == 1:
        fail(
            problems,
            "more than one ingress is annotated for cert-manager while sharing a "
            "single TLS secretName. Annotate exactly one; the cert is served for "
            "the host by SNI regardless of which Ingress created the router.",
        )


def check_external_domain_matches_ingress(values: dict, problems: list[str]) -> None:
    external_domain = values.get("zitadel", {}).get("configmapConfig", {}).get("ExternalDomain")
    if not external_domain:
        fail(problems, "zitadel.configmapConfig.ExternalDomain is unset.")
        return
    hosts = {
        host.get("host")
        for _, block in _ingress_blocks(values)
        if block.get("enabled")
        for host in (block.get("hosts") or [])
        if host.get("host")
    }
    mismatched = sorted(h for h in hosts if h != external_domain)
    if mismatched:
        fail(
            problems,
            f"ExternalDomain is {external_domain!r} but ingress hosts include "
            f"{mismatched}. Zitadel bakes ExternalDomain into the OIDC issuer URL "
            f"and every redirect URI; a mismatch means login starts and the "
            f"redirect back lands nowhere.",
        )
    if values.get("zitadel", {}).get("configmapConfig", {}).get("ExternalSecure") is True:
        port = values["zitadel"]["configmapConfig"].get("ExternalPort")
        if port != 443:
            fail(
                problems,
                f"ExternalSecure is true but ExternalPort is {port!r}. Behind a "
                f"TLS-terminating ingress it must be 443, or the issuer URL "
                f"carries the wrong port.",
            )


def render_with_helm(problems: list[str], required: bool) -> None:
    if shutil.which("helm") is None:
        message = "helm is not installed; skipped the chart render."
        if required:
            fail(problems, message)
        else:
            print(f"  note: {message}")
        return
    result = subprocess.run(  # noqa: S603
        [
            "helm",
            "template",
            "zitadel",
            CHART,
            "--version",
            CHART_VERSION,
            "-n",
            "evidara",
            "-f",
            str(VALUES),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        hint = detail[-1] if detail else "(no output)"
        message = f"`helm template {CHART} --version {CHART_VERSION}` failed: {hint}"
        # A missing repo/network is an environment problem, not a values problem.
        if "no cached repo found" in hint or "not found" in hint.lower():
            message += (
                "  (run `helm repo add zitadel https://charts.zitadel.com "
                "&& helm repo update zitadel` first)"
            )
            if not required:
                print(f"  note: {message}")
                return
        fail(problems, message)
        return
    print(f"  OK: chart {CHART}@{CHART_VERSION} renders with these values.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--render",
        action="store_true",
        help="require a successful `helm template` of the chart with these values",
    )
    args = parser.parse_args()

    if not VALUES.exists():
        print(f"FAIL: {VALUES.relative_to(REPO_ROOT)} does not exist.")
        return 1

    raw = VALUES.read_text(encoding="utf-8")
    values = yaml.safe_load(raw) or {}
    problems: list[str] = []

    check_no_committed_credentials(values, raw, problems)
    check_bundled_postgres_off(values, problems)
    check_ingress(values, problems)
    check_external_domain_matches_ingress(values, problems)
    render_with_helm(problems, required=args.render)

    if problems:
        print(f"FAIL: {VALUES.relative_to(REPO_ROOT)}")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"OK: {VALUES.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
