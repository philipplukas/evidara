"""Unit tests for lawyer-journey-kpis (no external deps).

Mirrors the loader pattern used by other `scripts/` tests: import the
script-as-module via importlib so the hyphenated filename works.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "lawyer-journey-kpis.py"
    name = "_lawyer_journey_kpis_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


FIXTURE_JSONL = """
{"name":"search.executed","query":"foo","resultCount":10,"sessionId":"s1","timestamp":"2026-04-24T10:00:00Z"}
{"name":"result.focused_from_list","resultId":"doc-1","sessionId":"s1","timestamp":"2026-04-24T10:01:00Z"}
{"name":"search.refined","query":"foo","resultCount":5,"sessionId":"s1","timestamp":"2026-04-24T10:02:00Z"}
{"name":"filter.reset_all","hadActiveConstraints":true,"sessionId":"s1","timestamp":"2026-04-24T10:03:00Z"}
{"name":"search.executed","query":"bar","resultCount":3,"sessionId":"s2","timestamp":"2026-04-24T11:00:00Z"}
{"name":"result.focused_from_list","resultId":"doc-2","sessionId":"s2","timestamp":"2026-04-24T11:02:00Z"}
{"name":"search.executed","query":"baz","resultCount":0,"sessionId":"s2","timestamp":"2026-04-24T11:30:00Z"}
""".strip()


class LawyerJourneyKpisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load_module()

    def _parse(self, text: str):
        lines = text.splitlines()
        return self.m.parse_events(lines, stderr=io.StringIO())

    def test_three_kpis_on_inline_fixture(self):
        """3 searches, 2 focuses within 5 min, 1 reset, 1 refinement, 2 sessions.

        The third search (11:30) is 28 min after the 11:00 focus → same
        sessionId ``s2`` but beyond the 5-min idle gap, so it opens a new
        session. Final session count = 3 (s1, s2-first, s2-second).
        """
        events, malformed, bad_ts = self._parse(FIXTURE_JSONL)
        self.assertEqual(malformed, 0)
        self.assertEqual(bad_ts, 0)
        self.assertEqual(len(events), 7)

        result = self.m.compute_kpis(events)
        self.assertEqual(result.total_searches, 3)
        self.assertEqual(result.focused_after_search, 2)
        self.assertEqual(result.reset_all_count, 1)
        self.assertEqual(result.refinement_count, 1)
        # Session idle-gap split: s1 = 1 session; s2 splits at 11:30 into 2.
        self.assertEqual(result.session_count, 3)

        self.assertAlmostEqual(result.focus_rate, 2 / 3, places=6)
        self.assertAlmostEqual(result.reset_per_search, 1 / 3, places=6)
        self.assertAlmostEqual(result.refinements_per_session, 1 / 3, places=6)

    def test_malformed_line_skipped_without_crash(self):
        mixed = (
            '{"name":"search.executed","query":"q","resultCount":1,'
            '"sessionId":"s","timestamp":"2026-04-24T09:00:00Z"}\n'
            "this-is-not-json\n"
            '{"missing":"name-field"}\n'
            '{"name":"result.focused_from_list","resultId":"r","sessionId":"s",'
            '"timestamp":"2026-04-24T09:01:00Z"}\n'
        )
        events, malformed, bad_ts = self._parse(mixed)
        self.assertEqual(malformed, 2)  # bad JSON + missing name
        self.assertEqual(bad_ts, 0)
        self.assertEqual(len(events), 2)

        result = self.m.compute_kpis(events)
        self.assertEqual(result.total_searches, 1)
        self.assertEqual(result.focused_after_search, 1)

    def test_empty_input_exits_with_code_two(self):
        stdin_backup = sys.stdin
        stderr_backup = sys.stderr
        stdout_backup = sys.stdout
        sys.stdin = io.StringIO("")
        sys.stderr = io.StringIO()
        sys.stdout = io.StringIO()
        try:
            code = self.m.main([])
        finally:
            sys.stdin = stdin_backup
            sys.stderr = stderr_backup
            sys.stdout = stdout_backup
        self.assertEqual(code, 2)

    def test_no_session_id_falls_back_to_global_aggregation(self):
        text = (
            '{"name":"search.executed","query":"q","resultCount":1,'
            '"timestamp":"2026-04-24T09:00:00Z"}\n'
            '{"name":"result.focused_from_list","resultId":"r",'
            '"timestamp":"2026-04-24T09:02:00Z"}\n'
        )
        events, _, _ = self._parse(text)
        result = self.m.compute_kpis(events)
        self.assertFalse(result.had_session_key)
        self.assertEqual(result.session_count, 1)
        self.assertEqual(result.focused_after_search, 1)


if __name__ == "__main__":
    unittest.main()
