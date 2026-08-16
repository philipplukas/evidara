"""Result recording: every experiment emits the six items the spec requires.

Spec section 25 -- figure, ground truth, estimate, error, identifiability status,
control experiment -- plus a machine-readable JSON dump that
``experiments/build_report.py`` aggregates into ``results/SYNTHETIC_SPEECH_REPORT.md``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

__all__ = ["Finding", "ExperimentRun", "results_dir", "jsonable"]


def results_dir() -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR


def jsonable(obj: Any) -> Any:
    """Convert numpy scalars/arrays into JSON-safe values."""
    if isinstance(obj, np.ndarray):
        return np.round(obj, 8).tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


@dataclass
class Finding:
    """One question the experiment asked, with its answer and its verdict."""

    question: str
    ground_truth: Any
    estimate: Any
    error: float | None
    status: str
    control: str = ""
    notes: str = ""
    error_label: str = "relative error"

    def to_dict(self) -> dict:
        return jsonable(asdict(self))


@dataclass
class ExperimentRun:
    """Collects findings, scalars and figure paths for one experiment script."""

    name: str
    title: str
    findings: list[Finding] = field(default_factory=list)
    scalars: dict[str, Any] = field(default_factory=dict)
    figures: list[str] = field(default_factory=list)
    tables: dict[str, Any] = field(default_factory=dict)

    def add(self, finding: Finding) -> Finding:
        self.findings.append(finding)
        return finding

    def record(self, **kwargs) -> Finding:
        return self.add(Finding(**kwargs))

    def scalar(self, key: str, value: Any) -> None:
        self.scalars[key] = jsonable(value)

    def table(self, key: str, value: Any) -> None:
        self.tables[key] = jsonable(value)

    def figure(self, path: Path | str) -> None:
        self.figures.append(str(Path(path).name))

    def save(self) -> Path:
        out = results_dir() / f"{self.name}.json"
        payload = {
            "name": self.name,
            "title": self.title,
            "figures": self.figures,
            "scalars": jsonable(self.scalars),
            "tables": jsonable(self.tables),
            "findings": [f.to_dict() for f in self.findings],
        }
        out.write_text(json.dumps(payload, indent=2))
        return out

    def print_summary(self, stream=sys.stdout) -> None:
        print(f"\n=== {self.title} ===", file=stream)
        for k, v in self.scalars.items():
            print(f"  {k}: {v}", file=stream)
        for f in self.findings:
            err = "n/a" if f.error is None or not np.isfinite(f.error) else f"{f.error:.4g}"
            print(f"  [{f.status:<24}] {f.question}  ({f.error_label} = {err})", file=stream)
            if f.control:
                print(f"      control: {f.control}", file=stream)
            if f.notes:
                print(f"      note:    {f.notes}", file=stream)
