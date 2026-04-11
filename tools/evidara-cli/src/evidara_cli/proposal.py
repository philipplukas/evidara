"""DSPy-optional source spec proposal module.

Provides a ``propose_source_spec`` function that returns a structured
acquisition spec from a seed URL.  It uses a rule-based heuristic by default
and falls back to a DSPy-assisted implementation only when:

1. ``dspy`` is installed in the environment, and
2. the environment variable ``EVIDARA_DSPY_ENABLED=1`` is set.

This makes DSPy strictly optional: operators and agents get consistent
rule-based behaviour in all environments that do not have DSPy, while
environments that opt in can benefit from learned proposal quality.

See ADR-0022 and docs/architecture/agentic-cli-workflow-architecture.md.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_DSPY_AVAILABLE: bool = False
try:
    import dspy  # type: ignore[import-untyped]  # noqa: F401

    _DSPY_AVAILABLE = True
except ImportError:
    pass


def _rule_based_proposal(seed_url: str, name: str | None) -> dict[str, Any]:
    """Deterministic rule-based proposal from a seed URL."""
    domain = re.sub(r"^https?://", "", seed_url).split("/")[0]
    suggested_name = name or re.sub(r"[^a-z0-9-]", "-", domain.lower()).strip("-")
    return {
        "name": suggested_name,
        "seed_url": seed_url,
        "acquisition_strategy": "crawl",
        "content_types": ["application/pdf", "text/html"],
        "confidence": 0.7,
        "rationale": f"Rule-based proposal from seed domain {domain!r}.",
        "suggested_tags": ["auto-proposed"],
        "requires_review": True,
        "dspy_assisted": False,
    }


def _dspy_proposal(seed_url: str, name: str | None) -> dict[str, Any]:
    """DSPy-assisted source spec proposal.

    Called only when ``dspy`` is installed and ``EVIDARA_DSPY_ENABLED=1``.
    Falls back to the rule-based proposal if the DSPy call fails.
    """
    import dspy  # type: ignore[import-untyped]

    class SourceSpecSignature(dspy.Signature):
        """Propose a structured source acquisition specification from a seed URL."""

        seed_url: str = dspy.InputField(desc="The seed URL for the document source")
        name_hint: str = dspy.InputField(desc="Optional name hint; may be empty")
        proposal: str = dspy.OutputField(
            desc=(
                "JSON-formatted acquisition spec with keys: "
                "name, acquisition_strategy, content_types, rationale"
            )
        )

    try:
        predictor = dspy.Predict(SourceSpecSignature)
        result = predictor(seed_url=seed_url, name_hint=name or "")
        parsed: dict[str, Any] = json.loads(result.proposal)
    except Exception as exc:  # noqa: BLE001
        import sys

        print(
            f"[evidara-cli] DSPy proposal failed ({exc!r}); falling back to rule-based.",
            file=sys.stderr,
        )
        return _rule_based_proposal(seed_url, name)

    parsed["seed_url"] = seed_url
    parsed.setdefault("confidence", 0.8)
    parsed.setdefault("suggested_tags", ["dspy-proposed"])
    parsed["dspy_assisted"] = True
    parsed["requires_review"] = True
    return parsed


def propose_source_spec(seed_url: str, name: str | None = None) -> dict[str, Any]:
    """Propose a source acquisition spec from a seed URL.

    Uses DSPy if installed and ``EVIDARA_DSPY_ENABLED=1``, otherwise uses a
    deterministic rule-based proposal.

    Args:
        seed_url: Seed URL for the document source.
        name: Optional name hint; derived from the seed domain when omitted.

    Returns:
        Proposed spec dict with ``name``, ``seed_url``, ``acquisition_strategy``,
        ``content_types``, ``confidence``, ``rationale``, ``requires_review``,
        and ``dspy_assisted`` keys.
    """
    if _DSPY_AVAILABLE and os.environ.get("EVIDARA_DSPY_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return _dspy_proposal(seed_url, name)
    return _rule_based_proposal(seed_url, name)
