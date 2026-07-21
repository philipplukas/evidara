"""Pytest fixtures for the RIS pipeline evaluation."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).parent

# See scripts/ci_skip_guard.py (#690). This suite is a *data-integrity* gate, and a
# data-integrity gate that passes when the data is absent is not a gate:
# `test_eval_pipeline.py` skips when a golden fixture directory is missing (:41, :102)
# and when `document_intelligence` will not import (:92). All three turn the
# eval-golden-fixtures job green having processed nothing.
sys.path.insert(0, str(EVAL_DIR.parent / "scripts"))

from ci_skip_guard import CiSkipGuard  # noqa: E402

# Nothing is excused here. All 8 golden fixtures are tracked in git and
# `pip install -e ./document-intelligence[test]` is what both eval-ris jobs run, so a
# skip in this suite means the gate lost its input — which is exactly the signal we
# want, not one to allowlist away.
ALLOWED_SKIPS: dict[str, str] = {}


def pytest_configure(config: pytest.Config) -> None:
    """Forbid CI from skipping the eval gate (#690)."""
    config.pluginmanager.register(CiSkipGuard(ALLOWED_SKIPS), "ci-skip-guard")


@pytest.fixture(scope="session")
def eval_dir() -> Path:
    return EVAL_DIR


@pytest.fixture(scope="session")
def documents_catalog(eval_dir: Path) -> list[dict[str, Any]]:
    path = eval_dir / "documents.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="session")
def queries(eval_dir: Path) -> list[dict[str, Any]]:
    path = eval_dir / "queries.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="session")
def gold_answers(eval_dir: Path) -> dict[str, dict[str, Any]]:
    path = eval_dir / "gold_answers.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return {row["query_id"]: row for row in csv.DictReader(f)}
