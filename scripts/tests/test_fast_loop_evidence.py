"""Gate-coverage rendering in `scripts/fast-loop-evidence.sh` (#744).

The evidence markdown these tests exercise is the artifact an operator reads before
flipping `enabled: true` under ADR-0030. A gate that self-skipped must read as
skipped there — reporting it as a pass is the green-because-it-never-ran defect
this repo keeps paying for (#605, #675, #713).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_LIB = REPO_ROOT / "scripts" / "fast-loop-evidence.sh"


def render(summary: dict) -> str:
    """Source the shell library and render `summary` to evidence markdown."""
    with tempfile.TemporaryDirectory() as tmp:
        summary_path = Path(tmp) / "summary.json"
        output_path = Path(tmp) / "evidence-summary.md"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")

        result = subprocess.run(
            [
                "bash",
                "-c",
                f'source "{EVIDENCE_LIB}" && '
                f'render_fast_loop_evidence_markdown "{summary_path}" "{output_path}" "CH Fedlex"',
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"render failed: {result.stderr}")
        return output_path.read_text(encoding="utf-8")


BASE_CHECKS = {
    "captured_count": 3,
    "raw_artifact_count": 3,
    "accepted_count": 3,
    "processing_count": 3,
    "canonical_ready_count": 3,
    "processed_count": 3,
}


def summary(**checks: object) -> dict:
    return {
        "environment": "dev",
        "template_id": "gemeinde_http_zh_stadt_hundevorschriften",
        "source_id": "src_1",
        "source_version_id": "sv_1",
        "run_id": "run_1",
        "verdict": "pass",
        "checks": {**BASE_CHECKS, **checks},
    }


class GateCoverageTests(unittest.TestCase):
    def test_skipped_gate_is_named_and_marked_unverified(self) -> None:
        markdown = render(
            summary(skipped_gates=["title_ok", "indexed_language_ok"], title_ok=1)
        )

        self.assertIn("## Gate coverage", markdown)
        self.assertIn("`title_ok` — **skipped (not applicable to this template)**", markdown)
        self.assertIn("`indexed_language_ok` — **skipped", markdown)

    def test_skipped_gates_appear_in_the_paste_block(self) -> None:
        markdown = render(summary(skipped_gates=["title_ok"]))

        self.assertIn("> Skipped gates (not verified): `title_ok`.", markdown)

    def test_empty_skipped_gates_reports_full_coverage(self) -> None:
        markdown = render(summary(skipped_gates=[]))

        self.assertIn("None — every gate below was evaluated.", markdown)
        self.assertIn("> Skipped gates (not verified): none.", markdown)

    def test_run_without_the_key_is_unknown_not_covered(self) -> None:
        # The five sibling fast-loop scripts do not emit `skipped_gates` yet. Their
        # evidence must not claim a coverage they never reported.
        markdown = render(summary())

        self.assertIn("Unknown — this run did not report gate coverage.", markdown)
        self.assertNotIn("every gate below was evaluated", markdown)


class ContentTypeLabelTests(unittest.TestCase):
    def test_paste_block_labels_the_configured_content_type(self) -> None:
        markdown = render(
            summary(expect_content_type="application/pdf", content_type_match_count=3)
        )

        self.assertIn("application/pdf=`3`", markdown)

    def test_legacy_html_count_key_still_renders(self) -> None:
        # Sibling scripts still emit `content_type_html_count`; dropping the fallback
        # would silently render `text/html=0` for a run that captured resources.
        markdown = render(summary(content_type_html_count=7))

        self.assertIn("text/html=`7`", markdown)


if __name__ == "__main__":
    unittest.main()
