"""Tests for scripts/check_di_surface_config.py.

The regression is real and was live: between #971 (which shipped ADR-0057's retraction
job) and 2026-09-16, `infra/hetzner/apps/configmap.yaml` set the three explicit
`DI_PUBLISHED_*` / `DI_PROCESSING_MANIFESTS_URI` keys and **not**
`DI_CANONICAL_RETRACTIONS_URI`. `RuntimeSettings.from_env` takes the explicit branch when
any of those is present, and that branch does not derive the ledger — so
`document_intelligence_canonical_retract` raised `missing_retraction_ledger_config` and
removed nothing, while #806's known-wrong Bundesverfassung rows stayed in the served
index.

So the case that matters most is the **pre-fix configmap**: if the guard does not fail on
exactly what was deployed, it is decoration. That is `test_pre_fix_configmap_fails`.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_di_surface_config.py"

_spec = importlib.util.spec_from_file_location("check_di_surface_config", SCRIPT)
assert _spec and _spec.loader
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

# Verbatim shape of the block as it stood before the fix.
PRE_FIX = dedent("""\
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: evidara-config
    data:
      DI_ENVIRONMENT: "production"
      DI_PUBLISHED_DOCUMENTS_URI: "s3://evidara-lakehouse/canonical/published_documents"
      DI_PUBLISHED_SECTIONS_URI: "s3://evidara-lakehouse/canonical/published_sections"
      DI_PROCESSING_MANIFESTS_URI: "s3://evidara-lakehouse/canonical/processing_manifests"
      NATS_SERVERS: "nats://nats.evidara.svc:4222"
""")

FIXED = PRE_FIX + '  DI_CANONICAL_RETRACTIONS_URI: "s3://evidara-lakehouse/canonical/canonical_retractions"\n'

ROOT_BRANCH = dedent("""\
    apiVersion: v1
    kind: ConfigMap
    data:
      DI_SURFACES_ROOT_URI: "s3://evidara-canonical/surfaces"
""")


class CheckDiSurfaceConfigTest(unittest.TestCase):
    def _run_against(self, text: str) -> int:
        """Point the checker at a temporary configmap and return its exit code."""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "configmap.yaml"
            path.write_text(text, encoding="utf-8")
            original = checker.CONFIGMAP
            checker.CONFIGMAP = path
            try:
                return checker.main()
            finally:
                checker.CONFIGMAP = original

    def test_pre_fix_configmap_fails(self) -> None:
        """The exact deployed config that could not retract must be rejected."""
        self.assertEqual(self._run_against(PRE_FIX), 1)

    def test_fixed_configmap_passes(self) -> None:
        self.assertEqual(self._run_against(FIXED), 0)

    def test_root_branch_is_not_applicable(self) -> None:
        """DI_SURFACES_ROOT_URI derives the ledger, so the pairing is not required."""
        self.assertEqual(self._run_against(ROOT_BRANCH), 0)

    def test_non_s3_ledger_uri_is_rejected(self) -> None:
        """A local path here would write the ledger somewhere the cluster cannot read."""
        bad = PRE_FIX + '  DI_CANONICAL_RETRACTIONS_URI: "/tmp/retractions"\n'
        self.assertEqual(self._run_against(bad), 1)

    def test_the_real_configmap_is_currently_paired(self) -> None:
        """Guards the committed file, not just the checker's logic."""
        self.assertEqual(checker.main(), 0)

    def test_commented_out_key_does_not_count(self) -> None:
        """A key that is only mentioned in a comment must not satisfy the pairing."""
        commented = PRE_FIX + '  # DI_CANONICAL_RETRACTIONS_URI: "s3://.../canonical_retractions"\n'
        self.assertEqual(self._run_against(commented), 1)


if __name__ == "__main__":
    unittest.main()
