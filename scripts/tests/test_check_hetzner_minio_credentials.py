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
        checker.check_workload_manifests(
            problems,
            {
                account["k8s_secret"]
                for account in json.loads(
                    checker.ACCOUNTS_JSON.read_text(encoding="utf-8")
                )["accounts"]
            },
        )
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

    def _accounts_with_prefix(self, access: str, prefix: str = "") -> dict:
        return {
            "all_buckets": self.ALL_BUCKETS,
            "accounts": [
                {
                    "user": "demo",
                    "policy_file": "demo.json",
                    "k8s_secret": "evidara-s3-demo",
                    "access_key_field": "AK",
                    "secret_key_field": "SK",
                    "allow": [
                        {"bucket": "evidara-lakehouse", "access": access, "prefix": prefix}
                    ],
                    "deny": ["evidara-raw-artifacts", "evidara-pg-backups"],
                }
            ],
        }

    @staticmethod
    def _two_statement_policy(prefix: str, object_actions: list[str]) -> dict:
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "Bucket",
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
                    "Resource": ["arn:aws:s3:::evidara-lakehouse"],
                },
                {
                    "Sid": "Objects",
                    "Effect": "Allow",
                    "Action": object_actions,
                    "Resource": [f"arn:aws:s3:::evidara-lakehouse/{prefix}*"],
                },
            ],
        }

    def test_read_only_account_granted_write_is_rejected(self) -> None:
        """The exact escape the reviewer demonstrated: bucket sets are unchanged.

        `document-service` acquiring s3:PutObject on `canonical/*` lets a compromised
        read API corrupt the canonical surfaces legal-search indexes, and changes no
        bucket set at all.
        """
        accounts = self._accounts_with_prefix("ro", "canonical/")
        policy = self._two_statement_policy(
            "canonical/", ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        )
        problems = self._run(accounts, {"demo.json": policy})
        self.assertTrue(any("s3:PutObject" in p for p in problems), problems)

    def test_write_only_account_granted_read_is_rejected(self) -> None:
        """`platform-control` must not be able to read raw artifacts back."""
        accounts = self._accounts_with_prefix("wo")
        policy = self._two_statement_policy("", ["s3:PutObject", "s3:GetObject"])
        problems = self._run(accounts, {"demo.json": policy})
        self.assertTrue(any("s3:GetObject" in p for p in problems), problems)

    def test_object_resource_outside_the_declared_prefix_is_rejected(self) -> None:
        """A bucket-root grant makes the account's in-prefix deny probe meaningless."""
        accounts = self._accounts_with_prefix("ro", "canonical/")
        policy = self._two_statement_policy("", ["s3:GetObject"])
        problems = self._run(accounts, {"demo.json": policy})
        self.assertTrue(any("prefix" in p for p in problems), problems)

    def test_bucket_level_admin_action_is_rejected(self) -> None:
        """`s3:*` on a bucket ARN includes s3:DeleteBucket."""
        accounts = self._accounts_with_prefix("rw")
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "Everything",
                    "Effect": "Allow",
                    "Action": ["s3:*"],
                    "Resource": ["arn:aws:s3:::evidara-lakehouse"],
                }
            ],
        }
        problems = self._run(accounts, {"demo.json": policy})
        self.assertTrue(any("s3:*" in p for p in problems), problems)

    def test_declared_bucket_with_no_grant_is_rejected(self) -> None:
        accounts = self._accounts_with_prefix("ro", "canonical/")
        empty = {"Version": "2012-10-17", "Statement": []}
        problems = self._run(accounts, {"demo.json": empty})
        self.assertTrue(any("grants nothing there" in p for p in problems), problems)

    def test_matching_policy_passes(self) -> None:
        accounts = self._accounts_with_prefix("rw", "canonical/")
        policy = self._two_statement_policy(
            "canonical/", ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        )
        self.assertEqual(self._run(accounts, {"demo.json": policy}), [])

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


class CheckWorkloadManifestsTest(unittest.TestCase):
    """Checking only the values files and deploy-stage4.sh left the obvious hole.

    Adding `- secretRef: {name: minio-root}` to `apps/platform-control.yaml` put root
    straight back into a running pod, and the guard reported "no workload uses root".
    """

    def _run(self, manifests: dict[str, str], known: set[str] | None = None) -> list[str]:
        with TemporaryDirectory() as tmp:
            hetzner = Path(tmp) / "infra" / "hetzner"
            (hetzner / "apps").mkdir(parents=True)
            (hetzner / "values").mkdir(parents=True)
            for name, body in manifests.items():
                (hetzner / name).write_text(body, encoding="utf-8")

            original = (checker.HETZNER, checker.REPO_ROOT)
            checker.HETZNER, checker.REPO_ROOT = hetzner, Path(tmp)
            try:
                problems: list[str] = []
                checker.check_workload_manifests(
                    problems, known if known is not None else {"evidara-s3-platform-control"}
                )
                return problems
            finally:
                checker.HETZNER, checker.REPO_ROOT = original

    CLEAN = dedent("""\
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: platform-control-api
        spec:
          template:
            spec:
              containers:
                - name: api
                  envFrom:
                    - secretRef:
                        name: evidara-s3-platform-control
    """)

    ROOT_SECRET_REF = dedent("""\
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: platform-control-api
        spec:
          template:
            spec:
              containers:
                - name: api
                  envFrom:
                    - secretRef:
                        name: minio-root
    """)

    ROOT_SECRET_KEY_REF = dedent("""\
        server:
          workers: 1
        env:
          - name: MINIO_SECRET_KEY
            valueFrom:
              secretKeyRef:
                name: minio-root
                key: rootPassword
    """)

    def test_clean_manifest_passes(self) -> None:
        self.assertEqual(self._run({"apps/platform-control.yaml": self.CLEAN}), [])

    def test_secret_ref_to_root_is_rejected(self) -> None:
        problems = self._run({"apps/platform-control.yaml": self.ROOT_SECRET_REF})
        self.assertTrue(any("minio-root" in p for p in problems), problems)

    def test_secret_key_ref_to_root_in_a_values_file_is_rejected(self) -> None:
        """A NEW values file must not be able to smuggle root in either."""
        problems = self._run({"values/some-new-chart.yaml": self.ROOT_SECRET_KEY_REF})
        self.assertTrue(any("minio-root" in p for p in problems), problems)

    def test_reference_to_an_unprovisioned_scoped_secret_is_rejected(self) -> None:
        """A typo'd `evidara-s3-*` name yields a pod with no credential at all."""
        problems = self._run({"apps/platform-control.yaml": self.CLEAN}, known={"other"})
        self.assertTrue(any("no account" in p for p in problems), problems)

    def test_real_repo_manifests_pass(self) -> None:
        known = {
            account["k8s_secret"]
            for account in json.loads(checker.ACCOUNTS_JSON.read_text(encoding="utf-8"))[
                "accounts"
            ]
        }
        problems: list[str] = []
        checker.check_workload_manifests(problems, known)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
