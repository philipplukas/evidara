"""Every `runs-on:` fallback must name a scale set that is actually deployed.

Workflows select a self-hosted pool with:

    runs-on: ${{ vars.HEAVY_RUNNER_SCALE_SET || 'evidara-heavy-v2' }}

The repo Actions variable is set today, so the literal after `||` is dead code --
right up until the variable is renamed, deleted, or unset on a fork, at which
point it becomes the value that decides where the job runs.

Three workflows carried `'evidara-heavy'` while the deployed scale set has been
`evidara-heavy-v2` since the v2 rebuild. In ARC's gha-runner-scale-set mode the
scale set *name* is the routing key, and a job queued against a name no runner
answers to does not fail -- it queues forever, until someone notices a PR that
has been "running" for hours. That is the failure this guard exists to prevent.

The canonical names are parsed out of `deploy-runners.sh` rather than hardcoded
here, so renaming a pool in one place cannot leave this test asserting the old
name.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "infra" / "hetzner" / "deploy-runners.sh"
WORKFLOWS = ROOT / ".github" / "workflows"

FALLBACK_RE = re.compile(
    r"vars\.(?P<pool>LIGHT|HEAVY)_RUNNER_SCALE_SET\s*\|\|\s*'(?P<fallback>[^']+)'"
)


def _canonical_names() -> dict[str, str]:
    """LIGHT/HEAVY scale-set names as deploy-runners.sh actually installs them."""
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    names = {}
    for pool in ("LIGHT", "HEAVY"):
        match = re.search(rf"^{pool}_NAME=(\S+)", source, re.MULTILINE)
        if match:
            names[pool] = match.group(1).strip("\"'")
    return names


class RunnerScaleSetFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.canonical = _canonical_names()

    def test_deploy_script_declares_both_pool_names(self) -> None:
        # If this fails the parsing above is stale, and every assertion below
        # would silently degrade into "compare against nothing".
        self.assertEqual(
            set(self.canonical),
            {"LIGHT", "HEAVY"},
            f"could not parse LIGHT_NAME/HEAVY_NAME from {DEPLOY_SCRIPT}",
        )

    def test_every_workflow_fallback_matches_the_deployed_scale_set(self) -> None:
        offenders = []
        found = 0
        for workflow in sorted(WORKFLOWS.glob("*.yml")):
            for match in FALLBACK_RE.finditer(workflow.read_text(encoding="utf-8")):
                found += 1
                pool = match.group("pool")
                fallback = match.group("fallback")
                if fallback != self.canonical[pool]:
                    offenders.append(
                        f"{workflow.name}: {pool} falls back to '{fallback}', "
                        f"but the deployed scale set is '{self.canonical[pool]}'"
                    )
        self.assertGreater(found, 0, "no runner scale-set fallbacks found — regex stale?")
        self.assertEqual(
            offenders,
            [],
            "A job queued against an undeployed scale set queues forever rather than "
            "failing:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
