"""`scripts/replay-nats-dlq.sh` — the DLQ had no reader on this runtime.

`scripts/replay-dlq.sh` is a GCP Pub/Sub script and ADR-0029 retired that
runtime, so a dead-lettered event was a permanent silent loss with its payload
sitting in the stream. Measured 2026-09-17: 88 events (48 `document.processed`,
40 `document.processing_status.updated`) dead-lettered when the projection bridge
could not authenticate, leaving 59 documents with no `canonical_ready` in the
read model and 48 unprojected.

These cover the parts that do not need a cluster. The enumeration and publish
paths are exercised by `--dry-run` against a real stream, which is the only place
they can be.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "replay-nats-dlq.sh"
LEGACY = REPO_ROOT / "scripts" / "replay-dlq.sh"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
        env={"PATH": "/usr/bin:/bin", "HOME": str(REPO_ROOT)},
    )


class Interface(unittest.TestCase):
    def test_parses(self) -> None:
        self.assertEqual(
            subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode, 0
        )

    def test_help_exits_zero(self) -> None:
        proc = run("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--dry-run", proc.stdout)

    def test_unknown_flag_is_refused(self) -> None:
        proc = run("--nope")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Unknown argument", proc.stderr + proc.stdout)


class PublishSafety(unittest.TestCase):
    """Two flags that are not optional, and one that must not appear."""

    def setUp(self) -> None:
        self.source = SCRIPT.read_text(encoding="utf-8")

    def test_publishes_json_with_templates_disabled(self) -> None:
        # `nats pub` runs Go templates over the body by default. A replayed
        # payload is JSON and must be published verbatim.
        self.assertIn("--no-templates", self.source)

    def test_reads_the_body_from_stdin(self) -> None:
        # Passing a 2 KB JSON payload as an argv word would mangle it on the
        # first quote and expose it in the process table.
        self.assertIn("--force-stdin", self.source)

    def test_the_target_subject_is_the_dlq_subject_minus_the_suffix(self) -> None:
        # The derivation is a sed expression; assert it is anchored so
        # `a.dlq.b` cannot be rewritten in the middle.
        self.assertIn(r"sed 's/\.dlq\$//'", self.source)

    def test_it_never_drains_the_dlq(self) -> None:
        # Replaying must not delete the evidence. A `stream rmm` / purge here
        # would destroy the only copy of a payload if the republish failed.
        # Named operations only. An earlier version of this test forbade
        # "--force", which matches the REQUIRED "--force-stdin" and failed on a
        # correct script — the same over-broad-pattern mistake as the
        # first-article gate, caught here by the test failing rather than in
        # production.
        for destructive in ("stream rmm", "stream purge", "stream rm ", "stream del"):
            self.assertNotIn(
                destructive, self.source, f"{destructive!r} would remove the DLQ evidence"
            )

    def test_a_non_dlq_subject_is_skipped_not_republished(self) -> None:
        # The scan is by sequence range, so a non-DLQ message in range must be
        # skipped rather than republished onto itself.
        self.assertIn("is not a DLQ", self.source)


class LegacyScriptPointsHere(unittest.TestCase):
    def test_the_gcp_script_says_it_does_not_work_on_this_runtime(self) -> None:
        """A dead script that still reads as usable is worse than a deleted one.

        It is kept rather than removed because the Pub/Sub shape is the record of
        how the GCP runtime did this, but it must not be reached for first.
        """
        if not LEGACY.exists():
            self.skipTest("scripts/replay-dlq.sh has been removed")
        head = LEGACY.read_text(encoding="utf-8")[:2000]
        self.assertTrue(
            re.search(r"replay-nats-dlq\.sh", head),
            "replay-dlq.sh does not point at the NATS replacement",
        )
        self.assertTrue(
            re.search(r"ADR-0029|retired|does not work", head, re.I),
            "replay-dlq.sh does not say it is for the retired GCP runtime",
        )
