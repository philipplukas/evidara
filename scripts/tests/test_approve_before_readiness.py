"""Every fast-loop harness approves its source version BEFORE checking readiness (#998).

Production readiness requires an approved source version, and each harness creates
that version moments earlier. Asking first and approving second made
`--mode production` exit 1 every time on a fresh source:

    {"code":"mode_compatible_with_version_status","ok":false,
     "detail":"Production runs require an approved source version."}
    {"code":"acquisition_lock_open","ok":true,
     "detail":"Both ADR-0030 keys are turned: template enabled and provider live-ready."}

The lock was open. The driver was asking a question whose answer it was about to
change.

It went unnoticed because the nightly canary runs `acceptance`, whose readiness
does not require approval — so the path exercised daily was the one that worked,
and the failure appeared the first time someone asked for the mode the script
advertises in its own `--help`.

Only `ch-fedlex` and `ch-bger` take a `--mode` flag today, so only they could hit
it. The other five had the same ordering and would inherit the bug the moment one
gained a mode, which is why this asserts across the whole family rather than the
two that bit.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"

READINESS = re.compile(r'^log "==> Checking readiness"', re.M)
APPROVE = re.compile(r'^log "==> Approving source version"', re.M)


def drivers() -> list[Path]:
    """Every script that both approves a version and checks readiness."""
    found = [
        p
        for p in sorted(SCRIPTS.glob("*.sh"))
        if READINESS.search(p.read_text(encoding="utf-8"))
        and APPROVE.search(p.read_text(encoding="utf-8"))
    ]
    return found


class ApproveComesFirst(unittest.TestCase):
    def test_the_family_is_found(self) -> None:
        # Without this the assertions below pass over an empty list. Six fast-loop
        # harnesses plus ch-fedlex-compose-e2e.sh.
        self.assertGreaterEqual(
            len(drivers()), 7, f"expected >=7 drivers, found {[p.name for p in drivers()]}"
        )

    def test_approve_precedes_readiness_everywhere(self) -> None:
        offenders = []
        for p in drivers():
            source = p.read_text(encoding="utf-8")
            approve = APPROVE.search(source).start()
            readiness = READINESS.search(source).start()
            if approve > readiness:
                offenders.append(p.name)
        self.assertEqual(
            offenders,
            [],
            "these check readiness before approving, so --mode production cannot "
            f"dispatch on a fresh source: {offenders}",
        )

    def test_readiness_is_still_checked(self) -> None:
        """Reordering must not become deleting.

        The check is what refuses a closed ADR-0030 lock. Moving approve above it
        keeps both; removing it would make every harness dispatch blindly and
        would also make the test above pass.
        """
        for p in drivers():
            with self.subTest(script=p.name):
                source = p.read_text(encoding="utf-8")
                self.assertIn("/v1/runs/readiness", source)
                self.assertRegex(
                    source,
                    r'READY="\$\(jq -r \'\.ready\'',
                    f"{p.name} no longer reads .ready out of the response",
                )
                self.assertRegex(
                    source,
                    r'if \[\[ "\$\{READY\}" != "true" \]\]; then',
                    f"{p.name} no longer refuses when readiness is false",
                )

    def test_a_harness_that_queries_readiness_queries_the_mode_it_dispatches(self) -> None:
        """A harness must not check one mode and run another.

        Not a defect today — the four preview-only drivers hardcode `preview` in
        both places — but checking `preview` while dispatching `production` would
        reintroduce #998 from the other side, and pass the ordering test.
        """
        offenders = []
        for p in drivers():
            source = p.read_text(encoding="utf-8")
            query = re.search(r"readiness\?[^\"]*mode=([^\"&]*)", source)
            if not query:
                continue
            queried = query.group(1)
            declares_run_mode = re.search(r"^RUN_MODE=", source, re.M) is not None
            if declares_run_mode and "RUN_MODE" not in queried:
                offenders.append(f"{p.name} queries mode={queried} but has a --mode flag")
        self.assertEqual(offenders, [], "; ".join(offenders))
