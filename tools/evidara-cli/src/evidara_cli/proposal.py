"""DSPy-optional proposal module for evidara-cli.

Provides bounded proposal tasks (spec generation, summarisation) that may be backed by
rule-based stubs or, when DSPy is installed and a language-model backend is configured,
by optimisable DSPy modules.

Design rules (ADR-0022):
- DSPy is never a hard dependency.  The module must work without it.
- Proposal output must carry explicit inputs, outputs, and confidence metadata.
- Proposals never own irreversible control decisions.
"""

from __future__ import annotations

import importlib
import logging
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)

_DSPY_AVAILABLE: bool | None = None


def _dspy_available() -> bool:
    """Return True if DSPy is importable (lazy-checked once)."""
    global _DSPY_AVAILABLE  # noqa: PLW0603
    if _DSPY_AVAILABLE is None:
        _DSPY_AVAILABLE = importlib.util.find_spec("dspy") is not None
    return _DSPY_AVAILABLE


class SourceSpecProposal:
    """Propose an acquisition spec for a new source.

    Uses a rule-based stub by default.  When DSPy is available and a language-model
    backend is reachable, the stub is replaced by an optimisable DSPy module.

    Usage::

        proposal = SourceSpecProposal()
        result = proposal.propose(seed_url="https://example.com/laws")
        print(result["spec"])
    """

    def propose(
        self,
        seed_url: str,
        *,
        sampled_metadata: dict[str, Any] | None = None,
        existing_source_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a proposed acquisition spec.

        Args:
            seed_url: Canonical URL of the source to onboard.
            sampled_metadata: Optional HTTP metadata sampled from the target URL
                (e.g. content-type, page title, detected language).
            existing_source_names: Optional list of known source display names used to
                detect likely duplicates.

        Returns:
            A dict with keys:
            - ``spec``: proposed source spec fields
            - ``confidence``: float 0.0–1.0
            - ``rationale``: human-readable explanation
            - ``backend``: ``"rule-based"`` or ``"dspy"``
            - ``duplicate_risk``: ``"none"``, ``"low"``, or ``"high"``
        """
        if _dspy_available():
            try:
                return self._propose_dspy(
                    seed_url,
                    sampled_metadata=sampled_metadata,
                    existing_source_names=existing_source_names,
                )
            except Exception:
                logger.debug("DSPy proposal failed; falling back to rule-based stub", exc_info=True)

        return self._propose_rule_based(
            seed_url,
            sampled_metadata=sampled_metadata,
            existing_source_names=existing_source_names,
        )

    # ------------------------------------------------------------------
    # Rule-based stub
    # ------------------------------------------------------------------

    @staticmethod
    def _propose_rule_based(
        seed_url: str,
        *,
        sampled_metadata: dict[str, Any] | None,
        existing_source_names: list[str] | None,
    ) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(seed_url)
        host = parsed.hostname or seed_url
        # Derive a simple display name from the hostname.
        display_name = host.removeprefix("www.").split(".")[0].title()
        # Naive duplicate check by name similarity.
        duplicate_risk = "none"
        if existing_source_names:
            lower_names = [n.lower() for n in existing_source_names]
            if display_name.lower() in lower_names:
                duplicate_risk = "high"
            elif any(display_name.lower() in n for n in lower_names):
                duplicate_risk = "low"
        # Infer language from metadata or URL path.
        language = "de"
        if sampled_metadata:
            content_lang = sampled_metadata.get("content-language", "")
            if content_lang:
                language = str(content_lang).split(",")[0].strip().lower()

        spec: dict[str, Any] = {
            "display_name": display_name,
            "seed_url": seed_url,
            "hostname": host,
            "language": language,
            "acquisition_method": "web-crawl",
            "content_type_hint": sampled_metadata.get("content-type", "text/html")
            if sampled_metadata
            else "text/html",
        }
        return {
            "spec": spec,
            "confidence": 0.5,
            "rationale": (
                f"Rule-based stub derived display name '{display_name}' from host '{host}'. "
                "Review and adjust before applying."
            ),
            "backend": "rule-based",
            "duplicate_risk": duplicate_risk,
        }

    # ------------------------------------------------------------------
    # DSPy-backed module (loaded lazily)
    # ------------------------------------------------------------------

    @staticmethod
    def _propose_dspy(
        seed_url: str,
        *,
        sampled_metadata: dict[str, Any] | None,
        existing_source_names: list[str] | None,
    ) -> dict[str, Any]:
        """Produce a proposal using a DSPy ChainOfThought module.

        This is intentionally minimal: one forward pass, explicit inputs and outputs,
        no autonomous side effects.  The module should be optimised offline against a
        labelled eval set before replacing the rule-based stub in production.
        """
        import dspy  # type: ignore[import-not-found]  # noqa: PLC0415

        class _SpecSignature(dspy.Signature):  # type: ignore[misc]
            """Propose an Evidara source acquisition spec from a seed URL and optional metadata."""

            seed_url: str = dspy.InputField(desc="Canonical seed URL for the source.")
            sampled_metadata_json: str = dspy.InputField(
                desc="JSON-serialised HTTP metadata sampled from the URL, or empty string."
            )
            existing_names_csv: str = dspy.InputField(
                desc="Comma-separated list of existing source display names, or empty string."
            )
            display_name: str = dspy.OutputField(
                desc="Proposed short display name for the source (no spaces)."
            )
            language: str = dspy.OutputField(
                desc="Primary ISO 639-1 language code for documents at this source."
            )
            acquisition_method: str = dspy.OutputField(
                desc="Proposed acquisition method: web-crawl, api-feed, or file-batch."
            )
            rationale: str = dspy.OutputField(desc="One-sentence rationale for the proposed spec.")

        import json  # noqa: PLC0415

        module = dspy.ChainOfThought(_SpecSignature)
        result = module(
            seed_url=seed_url,
            sampled_metadata_json=json.dumps(sampled_metadata or {}),
            existing_names_csv=",".join(existing_source_names or []),
        )
        parsed = urllib.parse.urlparse(seed_url)
        host = parsed.hostname or seed_url
        duplicate_risk = "none"
        if existing_source_names and result.display_name:
            lower_names = [n.lower() for n in existing_source_names]
            dn = result.display_name.lower()
            if dn in lower_names:
                duplicate_risk = "high"
            elif any(dn in n for n in lower_names):
                duplicate_risk = "low"
        spec: dict[str, Any] = {
            "display_name": result.display_name,
            "seed_url": seed_url,
            "hostname": host,
            "language": result.language,
            "acquisition_method": result.acquisition_method,
        }
        return {
            "spec": spec,
            "confidence": 0.75,
            "rationale": result.rationale,
            "backend": "dspy",
            "duplicate_risk": duplicate_risk,
        }
