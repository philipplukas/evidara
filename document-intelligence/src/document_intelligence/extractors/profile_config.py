"""Per-step extraction profile configuration.

Extends the global DI_ENABLE_LLM_EXTRACTOR toggle with granular control
over individual extraction steps. See ADR-0023.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtractionProfileConfig:
    """Controls which DSPy extraction steps are active."""

    enable_title_extractor: bool = True
    enable_source_family_classifier: bool = True
    enable_commentary_extractor: bool = False
    llm_provider: str = "vertexai"
    llm_model: str = "gemini-2.0-flash"

    @classmethod
    def from_environment(cls, env: dict[str, Any] | None = None) -> ExtractionProfileConfig:
        source = env or os.environ
        return cls(
            enable_title_extractor=_parse_bool(
                source.get("DI_ENABLE_TITLE_EXTRACTOR", "true")
            ),
            enable_source_family_classifier=_parse_bool(
                source.get("DI_ENABLE_SOURCE_FAMILY_CLASSIFIER", "true")
            ),
            enable_commentary_extractor=_parse_bool(
                source.get("DI_ENABLE_COMMENTARY_EXTRACTOR", "false")
            ),
            llm_provider=str(
                source.get("DI_LLM_PROVIDER", "vertexai")
            ).strip().lower(),
            llm_model=str(
                source.get("DI_LLM_MODEL", "gemini-2.0-flash")
            ).strip(),
        )


def _parse_bool(raw_value: Any) -> bool:
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}
