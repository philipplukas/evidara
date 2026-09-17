"""`ART1_PATTERN` in ch-fedlex-fast-loop.sh — the first-article gate.

It is the only content gate that separates a complete document from a fragment
starting mid-text: `art_density_ok` counts markers and passes on a fragment just
as well. So it has to recognise the drafting conventions our corpora actually
use, and it has to keep meaning FIRST article.

Both halves were wrong before these tests existed. It knew only `Art. 1`, so:

  - SR 0.142.115.141, the 1875 Niederlassungsvertrag with Liechtenstein, failed.
    A complete document — preamble, Art. I to Art. VI, signatures — numbered in
    Roman numerals, whose only ARABIC "Art. 3" occurrences are cross-references
    to other agreements (measured 2026-09-17).
  - bare `Art\\. 1` also matched "Art. 12", so a fragment beginning at article 12
    satisfied a first-article check.

The pattern is read out of the script rather than duplicated here, so the two
cannot drift. It is exercised through `jq`, which is what evaluates it in
production — Python's `re` accepts the same lookaheads but is not the engine that
runs, and this file exists to test the engine that does.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "scripts" / "ch-fedlex-fast-loop.sh"

#: (text, expected, why). `expected` is 1 when the text should read as containing
#: a FIRST article, 0 otherwise.
CASES: list[tuple[str, int, str]] = [
    ("Art. 1 Zweck", 1, "Fedlex and most modern CH/AT acts"),
    ("Art. 1a Zweck", 1, "Art. 1a is still a first article"),
    ("§ 1 Zweck", 1, "BS/BL/AG/SO/LU/SH/TG/ZG and German Land law"),
    ("§1 Zweck", 1, "paragraph sign with no space"),
    ("Art. I3 Die Angehoerigen", 1, "1874 treaty: article I plus footnote marker"),
    ("Art. II4 Unter den", 0, "article II must not satisfy a first-article check"),
    ("Art. III und Art. IV", 0, "later Roman articles only"),
    ("Art. 3 der genannten Vereinbarungen", 0, "cross-reference to another act"),
    ("Art. 12 Schlussbestimmungen", 0, "Art. 12 is not Art. 1"),
    ("Art. 19 Inkrafttreten", 0, "Art. 19 is not Art. 1"),
    ("§ 14 Abs. 2", 0, "paragraph 14 is not paragraph 1"),
    ("§ 10 Gebuehren", 0, "paragraph 10 is not paragraph 1"),
    ("Navigation Kontakt Impressum Suche", 0, "a navigation shell is not law"),
]


def art1_pattern() -> str:
    """The single-quoted ART1_PATTERN assignment, as the shell would expand it."""
    source = HARNESS.read_text(encoding="utf-8")
    match = re.search(r"^ART1_PATTERN='([^']*)'$", source, re.M)
    assert match, "ART1_PATTERN assignment not found in ch-fedlex-fast-loop.sh"
    # VERBATIM. Inside single quotes the shell expands nothing, and `--arg` hands
    # jq the value with no further unescaping, so the characters in the script are
    # exactly the regex jq compiles.
    #
    # The first version of this helper re-applied a jq string-literal unescape
    # here. It made the tests pass against a pattern the script does not use,
    # while the real run reported art1_ok=0 on a document containing "Art. I3".
    # A test that normalises its input is testing itself.
    return match.group(1)


class FirstArticlePattern(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("jq") is None:
            # Not skipped: jq is a hard requirement of every driver in scripts/,
            # so its absence is a broken environment, not an inapplicable test.
            self.fail("jq is required by the fast-loop harnesses and is not installed")
        self.pattern = art1_pattern()

    def matches(self, text: str) -> int:
        proc = subprocess.run(
            ["jq", "-rs", "--arg", "p", self.pattern, "[.[]|select(test($p))]|length"],
            input=json.dumps(text),
            capture_output=True,
            text=True,
            check=True,
        )
        return int(proc.stdout.strip())

    def test_the_pattern_is_still_three_conventions(self) -> None:
        # Guards the extraction itself: a regex that failed to parse would make
        # every case below match nothing and read as a clean pass.
        for fragment in ("Art", "§", "I"):
            self.assertIn(fragment, self.pattern)

    def test_every_case(self) -> None:
        for text, expected, why in CASES:
            with self.subTest(why=why):
                self.assertEqual(
                    self.matches(text),
                    expected,
                    f"{why}: {text!r} against /{self.pattern}/",
                )

    def test_the_cases_cover_both_verdicts(self) -> None:
        # A table that only asserted matches would pass against `.` .
        self.assertGreaterEqual(sum(1 for _, e, _ in CASES if e == 1), 4)
        self.assertGreaterEqual(sum(1 for _, e, _ in CASES if e == 0), 4)
