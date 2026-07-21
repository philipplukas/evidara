"""Suite-wide pytest configuration for document-intelligence.

Exists to register the repo's "CI may not skip" guard (#690). This suite is where
that guard was needed most: #685 found 15 tests over the production LLM extraction
path executing nowhere — 11 of them dropped at collection by a module-level
`pytest.importorskip("dspy")`, which the suite reported without ever naming the file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# One implementation, shared across platform-control, document-intelligence and eval.
# See scripts/ci_skip_guard.py for why it lives there rather than being copied.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from ci_skip_guard import CiSkipGuard  # noqa: E402

# Skip reasons this suite excuses in CI, each with the argument for excusing it.
# Matched as substrings of the reason.
#
# The line drawn here: an *optional runtime backend*, selected by an environment
# variable and not exercised by the default production path, may skip. The default
# path may not. That is why `dspy` is no longer on this list — it backs the LLM
# metadata extractor that `processing_runtime.py:43` reaches for by default, so its
# tests now run in CI via the `llm` extra (#685) — while `docling` and `spacy`, which
# are opt-in parsers behind `DI_PARSER_BACKEND` / `DI_ENABLE_SPACY`, are still excused.
#
# Anything not listed here fails the run. Adding an entry means arguing for it here.
ALLOWED_SKIPS: dict[str, str] = {
    "DI_EVAL_LIVE not set": (
        "Live LLM evals call a paid API and need a key. They are a scheduled/manual "
        "quality gate, not a per-PR one; the mock path covers the plumbing on every run."
    ),
    "DI_EVAL_DOCLING not set": (
        "Live Docling eval — same reasoning as DI_EVAL_LIVE: it needs the heavy optional "
        "backend installed and is run deliberately, not per-PR."
    ),
    "docling-core not installed": (
        "Docling is an optional parser backend for text modalities, selected by "
        "DI_PARSER_BACKEND=docling (ADR-0038). It is opt-in per environment, so the "
        "default gate does not carry its dependency."
    ),
    "set EVIDARA_NATS_IT=1": (
        "NATS integration tests need a Docker daemon and are opt-in (ADR-0029). The "
        "unit-level consumer tests cover the same code paths without a broker."
    ),
    "spacy not installed": (
        "spaCy NER is opt-in behind DI_ENABLE_SPACY and lives in the `nlp` extra; it is "
        "not on the default extraction path."
    ),
}


def pytest_configure(config: pytest.Config) -> None:
    """Register the "CI may not skip" guard (#690).

    In CI, a skipped test — or a whole module dropped at collection — fails the run
    unless its reason appears in ALLOWED_SKIPS above.
    """
    config.pluginmanager.register(CiSkipGuard(ALLOWED_SKIPS), "ci-skip-guard")
