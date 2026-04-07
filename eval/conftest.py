"""Pytest fixtures for the RIS pipeline evaluation."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).parent


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
