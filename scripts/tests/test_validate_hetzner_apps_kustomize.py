"""Tests for scripts/validate_hetzner_apps_kustomize.sh.

That script replaced a gate which "passed" over an empty prod overlay, so its own
premise is that a check which cannot fail is not a check. It had no test of its
own, which meant the premise was unverified — and #884 landed two assertions in it
(the marketing workload, and the marketing Ingress) that would be exactly the kind
of thing to rot silently.

Each test here mutates a COPY of the real infra tree and asserts the script goes
red. Delete an assertion from the script and a named test below fails.

The script reports DID-NOT-RUN without kubectl, which is correct behaviour and not
something to assert around, so these skip in that case. CI installs kubectl for
this job.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_NAME = "validate_hetzner_apps_kustomize.sh"
SCRIPT = REPO_ROOT / "scripts" / SCRIPT_NAME

_HAVE_KUBECTL = shutil.which("kubectl") is not None


@unittest.skipUnless(_HAVE_KUBECTL, "kubectl is required to render the kustomization")
class ValidateHetznerAppsKustomizeTest(unittest.TestCase):
    def _run_against(self, mutate=None) -> subprocess.CompletedProcess[str]:
        """Copy scripts/ + infra/ into a temp root, optionally mutate, then run."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            shutil.copy(SCRIPT, root / "scripts" / SCRIPT_NAME)
            shutil.copytree(REPO_ROOT / "infra" / "hetzner", root / "infra" / "hetzner")
            if mutate is not None:
                mutate(root)
            return subprocess.run(
                ["bash", str(root / "scripts" / SCRIPT_NAME)],
                capture_output=True, text=True, timeout=180,
            )

    def test_the_real_tree_passes(self) -> None:
        """Without this, every test below could be satisfied by a script that always
        fails."""
        res = self._run_against()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_fails_when_marketing_leaves_the_kustomization(self) -> None:
        """#884's first half: marketing outside `resources:` is how it went 27 pin
        bumps without moving, and how it came to run a commit not on `main`."""

        def drop_marketing(root: Path) -> None:
            p = root / "infra" / "hetzner" / "apps" / "kustomization.yaml"
            p.write_text(p.read_text().replace("\n  - ../marketing\n", "\n"))

        res = self._run_against(drop_marketing)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("marketing", res.stderr)

    def test_fails_when_the_marketing_ingress_is_dropped(self) -> None:
        """#884's second half, and the one nothing measured: the Deployment and
        Service were applied and the Ingress never was, so a healthy pod served
        nobody. A workload assertion alone cannot see that — hence a separate one."""

        def drop_ingress(root: Path) -> None:
            p = root / "infra" / "hetzner" / "marketing" / "kustomization.yaml"
            p.write_text(p.read_text().replace("  - ingress-tls.yaml\n", ""))

        res = self._run_against(drop_ingress)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("Ingress", res.stderr)

    def test_fails_when_the_migrate_job_loses_its_presync_hook(self) -> None:
        """Pre-existing assertion, previously untested: without the hook Argo applies
        the Job alongside the workloads and the API can roll ahead of its migration."""

        def drop_hook(root: Path) -> None:
            p = root / "infra" / "hetzner" / "apps" / "migrate-job.yaml"
            p.write_text(p.read_text().replace("argocd.argoproj.io/hook: PreSync", "x-disabled: PreSync"))

        res = self._run_against(drop_hook)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("PreSync", res.stderr)


if __name__ == "__main__":
    unittest.main()
