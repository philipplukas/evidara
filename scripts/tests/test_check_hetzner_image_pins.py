"""Tests for scripts/check_hetzner_image_pins.py.

The regression under test is real: the migrate Job sat at 6e1816a7 while the apps
rolled at da39660d, and the resulting production database was one alembic revision
behind the code reading it. The Job reported success throughout — from its own older
image there was genuinely nothing left to apply — so nothing surfaced at deploy time.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_hetzner_image_pins.py"

_spec = importlib.util.spec_from_file_location("check_hetzner_image_pins", SCRIPT)
assert _spec and _spec.loader
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)

SHA_A = "a" * 40
SHA_B = "b" * 40

IMAGES = (
    "evidara-platform-control",
    "evidara-platform-control-admin",
    "evidara-legal-search-api",
    "evidara-legal-search-frontend",
    "evidara-document-intelligence-document-service",
    "evidara-document-intelligence-consumer",
)


def _kustomization(sha: str, *, odd_one_out: str | None = None) -> str:
    lines = ["apiVersion: kustomize.config.k8s.io/v1beta1", "kind: Kustomization", "images:"]
    for name in IMAGES:
        tag = odd_one_out if odd_one_out and name == IMAGES[-1] else sha
        lines.append(f"  - name: ghcr.io/philipplukas/{name}")
        lines.append(f"    newTag: {tag}")
    return "\n".join(lines) + "\n"


def _migrate_job(sha: str) -> str:
    return dedent(
        f"""\
        apiVersion: batch/v1
        kind: Job
        metadata:
          name: platform-control-migrate
        spec:
          template:
            spec:
              containers:
                - name: migrate
                  image: ghcr.io/philipplukas/evidara-platform-control:{sha}
        """
    )


def _marketing_deployment(sha: str) -> str:
    return dedent(
        f"""\
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: marketing
        spec:
          template:
            spec:
              containers:
                - name: marketing
                  image: ghcr.io/philipplukas/evidara-marketing:{sha}
        """
    )


class CheckHetznerImagePinsTest(unittest.TestCase):
    def _run(self, kustomization: str, migrate_job: str, extra: dict[str, str] | None = None) -> int:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            apps = root / "infra" / "hetzner" / "apps"
            apps.mkdir(parents=True)
            (apps / "kustomization.yaml").write_text(kustomization, encoding="utf-8")
            (apps / "migrate-job.yaml").write_text(migrate_job, encoding="utf-8")
            for rel, body in (extra or {}).items():
                target = root / "infra" / "hetzner" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")

            original = checker.REPO_ROOT
            checker.REPO_ROOT = root
            try:
                return checker.main()
            finally:
                checker.REPO_ROOT = original

    def test_passes_when_apps_and_migrate_job_share_a_sha(self) -> None:
        self.assertEqual(self._run(_kustomization(SHA_A), _migrate_job(SHA_A)), 0)

    def test_fails_when_the_migrate_job_lags_the_apps(self) -> None:
        """The #574-vs-da39660d drift: a successful migrate that applies nothing."""
        self.assertEqual(self._run(_kustomization(SHA_A), _migrate_job(SHA_B)), 1)

    def test_fails_when_the_app_images_disagree_with_each_other(self) -> None:
        self.assertEqual(
            self._run(_kustomization(SHA_A, odd_one_out=SHA_B), _migrate_job(SHA_A)), 1
        )

    def test_fails_on_a_moving_tag(self) -> None:
        self.assertEqual(self._run(_kustomization("latest"), _migrate_job("latest")), 1)

    def test_fails_when_the_migrate_job_has_no_platform_control_image(self) -> None:
        job = _migrate_job(SHA_A).replace(
            "ghcr.io/philipplukas/evidara-platform-control", "ghcr.io/philipplukas/busybox"
        )
        self.assertEqual(self._run(_kustomization(SHA_A), job), 1)

    def test_an_unkustomized_workload_may_roll_on_its_own_sha(self) -> None:
        """The marketing surface (ADR-0039) is deliberately outside apps/, so it is
        NOT required to share the platform's SHA — only to have one."""
        self.assertEqual(
            self._run(
                _kustomization(SHA_A),
                _migrate_job(SHA_A),
                extra={"marketing/deployment.yaml": _marketing_deployment(SHA_B)},
            ),
            0,
        )

    def test_fails_when_an_unkustomized_workload_uses_a_moving_tag(self) -> None:
        """Nothing transforms that tag, so `latest` there is rolled by whoever merges
        next rather than by whoever deploys."""
        self.assertEqual(
            self._run(
                _kustomization(SHA_A),
                _migrate_job(SHA_A),
                extra={"marketing/deployment.yaml": _marketing_deployment("latest")},
            ),
            1,
        )

    def test_helm_values_are_out_of_scope(self) -> None:
        """`runners/` and `values/` configure third-party charts applied by `helm
        upgrade`; the ARC pool really does run `:latest` and is excluded knowingly."""
        self.assertEqual(
            self._run(
                _kustomization(SHA_A),
                _migrate_job(SHA_A),
                extra={"runners/values-heavy.yaml": "        image: ghcr.io/philipplukas/evidara-runner-heavy:latest\n"},
            ),
            0,
        )

    def test_real_repo_files_are_consistent(self) -> None:
        """Guards the checked-in pins, not just the checker."""
        self.assertEqual(checker.main(), 0)


if __name__ == "__main__":
    unittest.main()
