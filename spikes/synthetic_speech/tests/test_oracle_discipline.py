"""Mechanical enforcement of the methodological rule (spec section 28).

Two rules, both checkable:

1. ``analysis/`` never imports a generator module. An estimator that can reach
   ``config.DEFAULT_ALPHA`` will eventually reach it.
2. Every line in ``experiments/`` that reads a ground-truth attribute of a ``Dataset``
   must be annotated, with one of two markers:

   * ``# GT``     -- the value is used for *scoring* or *reporting* (spec section 25
     requires every experiment to print the ground truth, so this must be allowed).
   * ``# ORACLE`` -- the value is fed *into* an estimator. Legitimate only in the
     experiments explicitly labelled oracle, and the marker makes each such use visible
     in a diff.

Without rule 2 it is far too easy to build a system that "recovers" the answer because
it was quietly handed the answer.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_MODULES = {"config", "dynamics", "acoustics", "noise", "generator"}

#: attributes of ``Dataset`` that are ground truth, not observations
GROUND_TRUTH_ATTRS = (
    "latent_u",
    "latent_du",
    "latent_d2u",
    "latent_u_speaker",
    ".clean",
    ".theta",
    ".alpha",
    ".phi",
    ".dyn",
    ".speakers",
    ".noise_model",
    'field="clean"',
)

MARKERS = ("# GT", "# ORACLE")


def _analysis_files() -> list[Path]:
    return sorted((ROOT / "analysis").glob("*.py"))


def _experiment_files() -> list[Path]:
    return sorted((ROOT / "experiments").glob("*.py"))


@pytest.mark.parametrize("path", _analysis_files(), ids=lambda p: p.name)
def test_analysis_never_imports_the_generator(path: Path):
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    leaked = imported & GENERATOR_MODULES
    assert not leaked, (
        f"{path.name} imports {sorted(leaked)}: analysis code must not be able to reach "
        "ground-truth parameters"
    )


@pytest.mark.parametrize("path", _experiment_files(), ids=lambda p: p.name)
def test_every_ground_truth_read_in_an_experiment_is_annotated(path: Path):
    offenders = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        code = line.split("#", 1)[0]
        if not any(attr in code for attr in GROUND_TRUTH_ATTRS):
            continue
        if not any(m in line for m in MARKERS):
            offenders.append(f"  {path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "ground-truth reads must be annotated '# GT' (scoring/reporting) or '# ORACLE' "
        "(fed to an estimator):\n" + "\n".join(offenders)
    )


def test_the_marker_rule_actually_catches_an_unmarked_read(tmp_path: Path):
    """Guard against the guard silently passing because the pattern never matches."""
    bad = tmp_path / "99_bad.py"
    bad.write_text("u = ds.latent_u.mean(0)\n")
    offenders = [
        line
        for line in bad.read_text().splitlines()
        if any(a in line.split("#", 1)[0] for a in GROUND_TRUTH_ATTRS)
        and not any(m in line for m in MARKERS)
    ]
    assert offenders
