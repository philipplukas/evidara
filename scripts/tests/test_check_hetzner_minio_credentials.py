"""Tests for scripts/check_hetzner_minio_credentials.py.

The regression under test is real and was live, not hypothetical: `rootPassword:
change-me-minio-root` sat on `main` from #504 and was the credential the Hetzner cluster
was actually running (#792). Trino carried the same string in `s3.aws-secret-key`.

So the cases that matter most here are the *pre-fix* files: if the guard does not fail
on exactly what was committed, it is decoration. Each is asserted below.
"""

from __future__ import annotations

import importlib.util
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
            name: minio-root
            key: rootPassword
    catalogs:
      iceberg: |
        connector.name=iceberg
        s3.aws-access-key=${ENV:MINIO_ACCESS_KEY}
        s3.aws-secret-key=${ENV:MINIO_SECRET_KEY}
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

    def test_real_repo_files_pass(self) -> None:
        """The committed files must satisfy the guard they ship with."""
        problems: list[str] = []
        checker.check_minio(problems)
        checker.check_trino(problems)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
