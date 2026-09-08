"""Tests for check_platform_contract_usage.py.

Per AGENTS.md: a guard ships with a test that fails when the guard is removed.
Each case here models a failure this estate actually had, so deleting a branch of
the guard turns a named test red rather than quietly widening what is allowed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_platform_contract_usage.py"

CONTRACT = textwrap.dedent(
    """\
    contractVersion: "1.1.0"
    ingress:
      classes: {public: traefik, tailnet: tailnet-ingress}
      issuers: {publicProd: letsencrypt-prod, publicStaging: letsencrypt-staging}
    s3:
      accounts:
        platform-control: {secret: evidara-s3-platform-control}
        cnpg-backup: {secret: cnpg-minio-backup}
    """
)


def run(tmp: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=tmp, capture_output=True, text=True
    )


def scaffold(tmp: Path, manifest: str) -> None:
    (tmp / "vendor").mkdir(parents=True, exist_ok=True)
    (tmp / "vendor" / "platform-contract.yaml").write_text(CONTRACT)
    apps = tmp / "infra" / "hetzner" / "apps"
    apps.mkdir(parents=True, exist_ok=True)
    (apps / "workload.yaml").write_text(manifest)


class PlatformContractUsageTests(unittest.TestCase):
    def test_passes_when_every_reference_is_declared(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            scaffold(
                tmp,
                "spec:\n  ingressClassName: traefik\n"
                "  secretKeyRef: {name: evidara-s3-platform-control}\n",
            )
            r = run(tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_rejects_an_s3_secret_the_contract_does_not_declare(self) -> None:
        # A typo'd Secret name is a Pod that never starts.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            scaffold(tmp, "spec:\n  secretKeyRef: {name: evidara-s3-typo-control}\n")
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("evidara-s3-typo-control", r.stdout)

    def test_rejects_an_undeclared_cluster_issuer(self) -> None:
        # This is the 36-day outage: an Ingress annotated with an issuer that does
        # not exist yields a certificate nobody trusts, and nothing else complains.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            scaffold(
                tmp,
                "metadata:\n  annotations:\n"
                "    cert-manager.io/cluster-issuer: letsencrypt-production\n",
            )
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("letsencrypt-production", r.stdout)

    def test_rejects_an_undeclared_ingress_class(self) -> None:
        # Which Traefik answers a hostname IS that hostname's exposure.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            scaffold(tmp, "spec:\n  ingressClassName: nginx\n")
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("nginx", r.stdout)

    def test_fails_loudly_when_the_vendored_contract_is_missing(self) -> None:
        # Absent must not read as "nothing to check".
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            scaffold(tmp, "spec: {}\n")
            os.remove(tmp / "vendor" / "platform-contract.yaml")
            r = run(tmp)
            self.assertEqual(r.returncode, 1)
            self.assertIn("missing", r.stdout.lower())


if __name__ == "__main__":
    unittest.main()
