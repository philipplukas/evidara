"""Unit tests for analyze_github_actions_queue (no gh network)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "analyze_github_actions_queue.py"
    name = "_analyze_github_actions_queue_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class AnalyzeGitHubActionsQueueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load_module()

    def test_percentile_two_values(self):
        self.assertEqual(self.m._percentile([10.0, 20.0], 50), 15.0)

    def test_runs_to_rows_queue_and_run(self):
        rows = self.m._runs_to_rows(
            [
                {
                    "databaseId": 1,
                    "workflowName": "W",
                    "conclusion": "success",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "startedAt": "2026-01-01T00:01:00Z",
                    "updatedAt": "2026-01-01T00:04:00Z",
                    "event": "push",
                    "headBranch": "main",
                }
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].queue_s, 60.0)
        self.assertEqual(rows[0].run_s, 180.0)
        self.assertEqual(rows[0].total_s, 240.0)

    def test_summarize_groups_workflows(self):
        r = self.m.RunRow(
            database_id=1,
            workflow_name="A",
            conclusion="success",
            event="push",
            head_branch="main",
            queue_s=0,
            run_s=10,
            total_s=10,
        )
        b = self.m.RunRow(
            database_id=2,
            workflow_name="B",
            conclusion="success",
            event="push",
            head_branch="main",
            queue_s=0,
            run_s=20,
            total_s=20,
        )
        s = self.m._summarize([r, b])
        self.assertEqual(set(s.keys()), {"A", "B"})
        self.assertEqual(s["A"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
