"""Tests for scripts/check_hetzner_minio_credentials.py.

The regression under test is real and was live, not hypothetical: `rootPassword:
change-me-minio-root` sat on `main` from #504 and was the credential the Hetzner cluster
was actually running (#792). Trino carried the same string in `s3.aws-secret-key`.

So the cases that matter most here are the *pre-fix* files: if the guard does not fail
on exactly what was committed, it is decoration. Each is asserted below.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_hetzner_minio_credentials.py"

_spec = importlib.util.spec_from_file_location("check_hetzner_minio_credentials", SCRIPT)
assert _spec and _spec.loader
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

# Verbatim from the files as they stood before #792 was fixed.
PRE_FIX_MINIO = dedent("""\
    mode: standalone
    rootUser: evidara
    rootPassword: change-me-minio-root
""")

PRE_FIX_TRINO = dedent("""\
    server:
      workers: 1
    catalogs:
      iceberg: |
        connector.name=iceberg
        s3.endpoint=http://minio.evidara.svc:9000
        s3.aws-access-key=evidara
        s3.aws-secret-key=change-me-minio-root
""")

FIXED_MINIO = dedent("""\
    mode: standalone
    existingSecret: minio-root
""")

FIXED_TRINO = dedent("""\
    server:
      workers: 1
    env:
      - name: MINIO_SECRET_KEY
        valueFrom:
          secretKeyRef:
            name: evidara-s3-trino
            key: secretKey
    catalogs:
      iceberg: |
        connector.name=iceberg
        s3.aws-access-key=${ENV:MINIO_ACCESS_KEY}
        s3.aws-secret-key=${ENV:MINIO_SECRET_KEY}
""")

# Verbatim from the file as it stood between #792 and #813: the credential is no longer
# committed, but it is still *root*, so a Trino compromise still reached the raw
# artifacts and the Postgres PITR backups.
ROOT_REFERENCING_TRINO = dedent("""\
    server:
      workers: 1
    env:
      - name: MINIO_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: minio-root
            key: rootUser
      - name: MINIO_SECRET_KEY
        valueFrom:
          secretKeyRef:
            name: minio-root
            key: rootPassword
    catalogs:
      iceberg: |
        connector.name=iceberg
        s3.aws-access-key=${ENV:MINIO_ACCESS_KEY}
        s3.aws-secret-key=${ENV:MINIO_SECRET_KEY}
""")

# Verbatim shape of the pre-#813 deploy-stage4.sh: root read out of `minio-root` and
# seeded into `evidara-app-secrets`, which every app mounts with envFrom.
PRE_813_STAGE4 = dedent("""\
    #!/usr/bin/env bash
    MINIO_USER="$(kubectl -n "$NS" get secret minio-root -o jsonpath='{.data.rootUser}' | base64 -d)"
    kubectl -n "$NS" create secret generic evidara-app-secrets \\
      --from-literal=PLATFORM_CONTROL_DATABASE_URL="postgresql+asyncpg://x" \\
      --from-literal=PLATFORM_CONTROL_S3_ACCESS_KEY_ID="${MINIO_USER}" \\
      --from-literal=DI_S3_SECRET_ACCESS_KEY="${MINIO_PW}" \\
      --dry-run=client -o yaml | kubectl apply -f -
""")

FIXED_STAGE4 = dedent("""\
    #!/usr/bin/env bash
    kubectl -n "$NS" create secret generic evidara-app-secrets \\
      --from-literal=PLATFORM_CONTROL_DATABASE_URL="postgresql+asyncpg://x" \\
      --dry-run=client -o yaml | kubectl apply -f -
""")


class CheckMinioCredentialsTest(unittest.TestCase):
    def _run(self, minio: str, trino: str) -> list[str]:
        """Point the checker at temp files and collect its problems."""
        with TemporaryDirectory() as tmp:
            minio_path = Path(tmp) / "minio.yaml"
            trino_path = Path(tmp) / "trino.yaml"
            minio_path.write_text(minio, encoding="utf-8")
            trino_path.write_text(trino, encoding="utf-8")

            original = (checker.MINIO_VALUES, checker.TRINO_VALUES, checker.REPO_ROOT)
            checker.MINIO_VALUES, checker.TRINO_VALUES = minio_path, trino_path
            checker.REPO_ROOT = Path(tmp)
            try:
                problems: list[str] = []
                checker.check_minio(problems)
                checker.check_trino(problems)
                return problems
            finally:
                checker.MINIO_VALUES, checker.TRINO_VALUES, checker.REPO_ROOT = original

    def test_pre_fix_minio_values_are_rejected(self) -> None:
        """The exact file that leaked must fail, or this guard proves nothing."""
        problems = self._run(PRE_FIX_MINIO, FIXED_TRINO)
        self.assertTrue(problems)
        self.assertTrue(any("rootPassword" in p for p in problems), problems)

    def test_pre_fix_trino_values_are_rejected(self) -> None:
        problems = self._run(FIXED_MINIO, PRE_FIX_TRINO)
        self.assertTrue(problems)
        self.assertTrue(any("s3.aws-secret-key" in p for p in problems), problems)

    def test_fixed_values_pass(self) -> None:
        self.assertEqual(self._run(FIXED_MINIO, FIXED_TRINO), [])

    def test_missing_existing_secret_is_rejected(self) -> None:
        """Deleting the password without adding the Secret leaves MinIO unbootable."""
        problems = self._run("mode: standalone\n", FIXED_TRINO)
        self.assertTrue(any("existingSecret" in p for p in problems), problems)

    def test_inline_password_alongside_existing_secret_is_rejected(self) -> None:
        """The chart prefers the inline value, so this silently defeats the Secret."""
        both = "existingSecret: minio-root\nrootPassword: something-else\n"
        problems = self._run(both, FIXED_TRINO)
        self.assertTrue(any("rootPassword" in p for p in problems), problems)

    def test_empty_root_password_is_allowed(self) -> None:
        """`rootPassword: \"\"` is the chart's own default and is not a credential."""
        values = 'existingSecret: minio-root\nrootPassword: ""\n'
        self.assertEqual(self._run(values, FIXED_TRINO), [])

    def test_prose_mentioning_the_credential_is_allowed(self) -> None:
        """Both files document the incident by name; only assignments are defects."""
        values = dedent("""\
            # The previous inline `rootPassword: change-me-minio-root` was live (#792).
            existingSecret: minio-root
        """)
        self.assertEqual(self._run(values, FIXED_TRINO), [])

    def test_trino_reading_the_root_secret_is_rejected(self) -> None:
        """#813: the credential stopped being committed, but it was still root."""
        problems = self._run(FIXED_MINIO, ROOT_REFERENCING_TRINO)
        self.assertTrue(any("minio-root" in p for p in problems), problems)

    def test_real_repo_files_pass(self) -> None:
        """The committed files must satisfy the guard they ship with."""
        problems: list[str] = []
        checker.check_minio(problems)
        checker.check_trino(problems)
        checker.check_stage4(problems)
        checker.check_policies(problems)
        self.assertEqual(problems, [])


class CheckStage4Test(unittest.TestCase):
    """`evidara-app-secrets` is mounted by every app; what is in it, all of them hold."""

    def _run(self, stage4: str) -> list[str]:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "deploy-stage4.sh"
            path.write_text(stage4, encoding="utf-8")
            original_stage4, original_root = checker.STAGE4, checker.REPO_ROOT
            checker.STAGE4, checker.REPO_ROOT = path, Path(tmp)
            try:
                problems: list[str] = []
                checker.check_stage4(problems)
                return problems
            finally:
                checker.STAGE4, checker.REPO_ROOT = original_stage4, original_root

    def test_pre_813_stage4_is_rejected(self) -> None:
        problems = self._run(PRE_813_STAGE4)
        self.assertTrue(any("minio-root" in p for p in problems), problems)
        self.assertTrue(any("PLATFORM_CONTROL_S3_ACCESS_KEY_ID" in p for p in problems), problems)
        self.assertTrue(any("DI_S3_SECRET_ACCESS_KEY" in p for p in problems), problems)

    def test_fixed_stage4_passes(self) -> None:
        self.assertEqual(self._run(FIXED_STAGE4), [])


class CheckPoliciesTest(unittest.TestCase):
    """A policy document that names no bucket, or every bucket, is root by another name."""

    ALL_BUCKETS = ["evidara-raw-artifacts", "evidara-lakehouse", "evidara-pg-backups"]

    def _run(self, accounts: dict, policies: dict[str, dict]) -> list[str]:
        with TemporaryDirectory() as tmp:
            policy_dir = Path(tmp) / "minio-policies"
            policy_dir.mkdir()
            (policy_dir / "accounts.json").write_text(json.dumps(accounts), encoding="utf-8")
            for name, body in policies.items():
                (policy_dir / name).write_text(json.dumps(body), encoding="utf-8")

            original = (checker.POLICY_DIR, checker.ACCOUNTS_JSON, checker.REPO_ROOT)
            checker.POLICY_DIR = policy_dir
            checker.ACCOUNTS_JSON = policy_dir / "accounts.json"
            checker.REPO_ROOT = Path(tmp)
            try:
                problems: list[str] = []
                checker.check_policies(problems)
                return problems
            finally:
                checker.POLICY_DIR, checker.ACCOUNTS_JSON, checker.REPO_ROOT = original

    def _accounts(self, allow: list[dict], deny: list[str]) -> dict:
        return {
            "all_buckets": self.ALL_BUCKETS,
            "accounts": [
                {
                    "user": "demo",
                    "policy_file": "demo.json",
                    "k8s_secret": "evidara-s3-demo",
                    "access_key_field": "AK",
                    "secret_key_field": "SK",
                    "allow": allow,
                    "deny": deny,
                }
            ],
        }

    @staticmethod
    def _policy(resources: list[str]) -> dict:
        return {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": resources}],
        }

    def test_scoped_policy_passes(self) -> None:
        accounts = self._accounts(
            allow=[{"bucket": "evidara-lakehouse", "access": "ro"}],
            deny=["evidara-raw-artifacts", "evidara-pg-backups"],
        )
        policies = {"demo.json": self._policy(["arn:aws:s3:::evidara-lakehouse/*"])}
        self.assertEqual(self._run(accounts, policies), [])

    def test_wildcard_resource_is_rejected(self) -> None:
        """`Resource: "*"` is exactly the grant #813 exists to remove."""
        accounts = self._accounts(
            allow=[{"bucket": "evidara-lakehouse", "access": "ro"}],
            deny=["evidara-raw-artifacts", "evidara-pg-backups"],
        )
        problems = self._run(accounts, {"demo.json": self._policy(["*"])})
        self.assertTrue(any("root by another name" in p for p in problems), problems)

    def test_policy_wider_than_declared_scope_is_rejected(self) -> None:
        """The deny test only checks what accounts.json declares; the policy must match."""
        accounts = self._accounts(
            allow=[{"bucket": "evidara-lakehouse", "access": "ro"}],
            deny=["evidara-raw-artifacts", "evidara-pg-backups"],
        )
        policies = {
            "demo.json": self._policy(
                ["arn:aws:s3:::evidara-lakehouse/*", "arn:aws:s3:::evidara-pg-backups/*"]
            )
        }
        problems = self._run(accounts, policies)
        self.assertTrue(any("wider than the tested scope" in p for p in problems), problems)

    def test_unclassified_bucket_is_rejected(self) -> None:
        """An unlisted bucket is an untested bucket."""
        accounts = self._accounts(
            allow=[{"bucket": "evidara-lakehouse", "access": "ro"}],
            deny=["evidara-raw-artifacts"],
        )
        policies = {"demo.json": self._policy(["arn:aws:s3:::evidara-lakehouse/*"])}
        problems = self._run(accounts, policies)
        self.assertTrue(any("evidara-pg-backups" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
