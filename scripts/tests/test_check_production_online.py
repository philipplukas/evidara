"""Tests for scripts/check-production-online.sh.

The script's whole value is that it distinguishes three outcomes — PASS, FAIL and
DID-NOT-RUN — against a live cluster. That is also exactly what rots silently: a
gate whose sections quietly stop asserting still prints a wall of green.

So these tests do not check formatting. Each one deletes or defeats a specific
guard's *input* and asserts the script goes red, and the healthy-scenario test
asserts it goes green — so a guard removed from the script fails a named test
here. Per AGENTS.md: a check whose test passes with the check deleted is
decoration.

The cluster is stubbed. `kubectl`, `curl`, `getent` and `openssl` are replaced by
shell scripts on PATH, so nothing here needs a cluster, a network, or Docker.

Note this covers a different question from test_check_hetzner_image_pins.py: that
one asserts the *manifests* agree with each other, statically. This one asserts
the running cluster agrees with `main`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-production-online.sh"

# The healthy scenario needs an image SHA that IS an ancestor of the ref the script
# compares against. Both are pinned to HEAD here rather than to `origin/main`: a CI
# checkout of a pull request has HEAD at the *merge* commit, which is by construction
# not an ancestor of `origin/main`, and `origin/main` may not be fetched at all at
# the configured depth. Comparing HEAD to HEAD is hermetic and tests the same logic.
def _head_sha() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


# Deliberately cannot exist. Some of these tests run without a kubectl stub, and CI
# runs on ARC runners INSIDE the target cluster — where a bare `kubectl` has working
# in-cluster credentials. Without this, a test meant to exercise the "no cluster"
# path instead queried live production and asserted against whatever it found there.
UNREACHABLE_NS = "evidara-no-such-namespace-for-tests"


DEPLOYS = ("platform-control-api", "legal-search-api")


def _kubectl_stub(*, ready: str = "1", image_sha: str, ingress_hosts: str) -> str:
    """A kubectl that answers only the queries the script actually makes."""
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        args="$*"
        case "$args" in
          *"config current-context"*) echo stub-context ;;
          *"get ns "*) exit 0 ;;
          *"applications.argoproj.io"*)
            if [[ "$args" == *jsonpath* ]]; then
              echo "evidara-apps Synced Healthy {image_sha}"
            fi
            exit 0 ;;
          *"get ingress"*) echo "{ingress_hosts}" ;;
          *"exec "*) echo 200 ;;
          *"get deploy "*"-n"*"--no-headers"*) echo "{DEPLOYS[0]}"; echo "{DEPLOYS[1]}" ;;
          *"spec.replicas"*)
            echo "{DEPLOYS[0]} 1 {ready}"
            echo "{DEPLOYS[1]} 1 1" ;;
          *"containers[0].image"*)
            echo "{DEPLOYS[0]} ghcr.io/philipplukas/evidara-platform-control:{image_sha}"
            echo "{DEPLOYS[1]} ghcr.io/philipplukas/evidara-legal-search-api:{image_sha}" ;;
          *readinessProbe*)
            echo "{DEPLOYS[0]} 8080 /health HTTP"
            echo "{DEPLOYS[1]} 8080 /health HTTP" ;;
          *".ports"*|*containerPort*) : ;;
          *"get deploy platform-control-api"*) exit 0 ;;
          *) : ;;
        esac
        """)


class ProductionOnlineCheckTest(unittest.TestCase):
    def _run(self, *, kubectl: str | None, env_extra: dict[str, str] | None = None,
             root: Path | None = None, curl_code: str = "200",
             resolves: bool = True) -> subprocess.CompletedProcess[str]:
        with TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            if kubectl is not None:
                (bindir / "kubectl").write_text(kubectl)
                (bindir / "kubectl").chmod(0o755)
            (bindir / "curl").write_text(
                f'#!/usr/bin/env bash\nprintf "%s" "{curl_code}"\n')
            (bindir / "curl").chmod(0o755)
            (bindir / "getent").write_text(
                "#!/usr/bin/env bash\nexit %d\n" % (0 if resolves else 2))
            (bindir / "getent").chmod(0o755)
            # No openssl on PATH: the expiry sub-check then simply does not run,
            # which is the behaviour under test everywhere else in these cases.
            env = {
                "PATH": f"{bindir}:{os.environ['PATH']}",
                "HOME": os.environ.get("HOME", tmp),
                # Never a real namespace: see UNREACHABLE_NS. Stubbed runs are
                # unaffected — the stub answers `get ns` for any name.
                "NAMESPACE": UNREACHABLE_NS,
                "GIT_REMOTE_REF": "HEAD",
            }
            env.update(env_extra or {})
            script = SCRIPT
            if root is not None:
                (root / "scripts").mkdir(parents=True, exist_ok=True)
                shutil.copy(SCRIPT, root / "scripts" / SCRIPT.name)
                script = root / "scripts" / SCRIPT.name
            return subprocess.run(
                ["bash", str(script)], capture_output=True, text=True, env=env, timeout=300)

    # ── the healthy baseline ─────────────────────────────────────────────────

    def test_healthy_cluster_passes(self):
        """With everything nominal the script must actually go green.

        Without this, every other test here could be satisfied by a script that
        always fails.
        """
        res = self._run(
            kubectl=_kubectl_stub(image_sha=_head_sha(), ingress_hosts=""),
            env_extra={"SKIP_EDGE": "1"},
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("FAIL", res.stdout)

    # ── one test per guard ───────────────────────────────────────────────────

    def test_unready_deployment_fails(self):
        """Guard: readiness. `Running` is not `Ready`."""
        res = self._run(
            kubectl=_kubectl_stub(ready="0", image_sha=_head_sha(), ingress_hosts=""),
            env_extra={"SKIP_EDGE": "1"},
        )
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("0/1 ready", res.stdout)

    def test_image_not_on_main_fails(self):
        """Guard: the running image must be a commit on the main line.

        This is the #884 defect — marketing served 32a13330, a pre-squash branch
        commit that is not on `main` — and no other check in the repo sees it.
        """
        res = self._run(
            kubectl=_kubectl_stub(image_sha="c" * 40, ingress_hosts=""),
            env_extra={"SKIP_EDGE": "1"},
        )
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("never seen", res.stdout)

    def test_unresolvable_declared_host_fails(self):
        """Guard: a hostname declared in an Ingress manifest must resolve.

        The other half of #884: `evidara.veyo.dev` had a manifest, a Deployment
        and a Service, and no DNS record — so the surface was healthy in every
        cluster-facing signal and unreachable to every human.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / "infra" / "hetzner").mkdir(parents=True)
            (root / "infra" / "hetzner" / "ing.yaml").write_text(
                "spec:\n  rules:\n    - host: nowhere.invalid\n")
            res = self._run(kubectl=None, root=root, resolves=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("does not resolve", res.stdout)

    def test_edge_5xx_fails(self):
        """Guard: the edge answering 5xx is a failure, 401 is not.

        401 means the auth proxy replied, which proves DNS, TLS, Traefik and the
        Ingress are all up. Treating it as a failure would make the script cry
        wolf on two of the four production hostnames.
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            (root / "infra" / "hetzner").mkdir(parents=True)
            (root / "infra" / "hetzner" / "ing.yaml").write_text(
                "spec:\n  rules:\n    - host: somewhere.invalid\n")
            bad = self._run(kubectl=None, root=root, curl_code="503")
            self.assertEqual(bad.returncode, 1, bad.stdout)
            self.assertIn("backend is not answering", bad.stdout)

            ok = self._run(kubectl=None, root=root, curl_code="401")
            self.assertIn("somewhere.invalid -> 401", ok.stdout)
            self.assertNotIn("somewhere.invalid ->", ok.stdout.replace(
                "somewhere.invalid -> 401", ""))

    # ── the three-outcome contract ───────────────────────────────────────────

    def test_missing_kubectl_is_did_not_run_never_pass(self):
        """A section whose prerequisites are absent must never read as a pass.

        This is the failure mode AGENTS.md names directly: `PASS`, `FAIL` and
        `DID-NOT-RUN` are three outcomes, and a gate that skips silently is how a
        terminal full of green comes to mean nothing.
        """
        res = self._run(kubectl=None, env_extra={"SKIP_EDGE": "1"})
        self.assertIn("DID-NOT-RUN", res.stdout)
        # Either prerequisite branch is acceptable — a workstation running this
        # test may well have a real kubectl on PATH pointed at another cluster.
        # What is not acceptable is either one reading as a pass.
        self.assertRegex(res.stdout, r"kubectl (not installed|cannot reach)")
        self.assertNotIn("every section ran and passed", res.stdout)
        self.assertNotIn("ONLINE", res.stdout)
        self.assertIn("UNKNOWN — nothing could be checked", res.stdout)


if __name__ == "__main__":
    unittest.main()
