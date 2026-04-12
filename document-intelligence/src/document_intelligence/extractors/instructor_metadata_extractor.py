"""Instructor-backed MetadataExtractor implementation.

Uses Pydantic models + Instructor for schema-validated LLM extraction
with auto-retry on validation failure. Replaces the DSPy-based extractor.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from document_intelligence.contracts.envelope import (
    ArtifactBundleManifest,
    ArtifactBundleManifestArtifact,
)
from document_intelligence.extractors.metadata import (
    MetadataExtractionCandidate,
    gather_metadata_hints_for_llm,
)
from document_intelligence.extractors.profile_config import ExtractionProfileConfig
from document_intelligence.normalize.ir import NormalizedDocumentIR

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 3000
_SYSTEM_PROMPT = (
    "You are a legal document metadata extractor. Given document text and metadata hints, "
    "extract the canonical title, classify the document source family, and rate your confidence."
)


class LegalDocumentMetadata(BaseModel):
    """Schema for LLM-extracted legal document metadata."""

    title: str = Field(description="Canonical title of the legal document")
    source_family: Literal["law", "decision", "commentary", "admin_guidance", "unknown"] = Field(
        description="Classification of the document type"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title must not be empty")
        return stripped


class CommentaryPassages(BaseModel):
    """Schema for commentary-specific extraction."""

    passages: list[str] = Field(default_factory=list, description="Key commentary passages")
    referenced_provisions: list[str] = Field(default_factory=list, description="Legal provisions referenced")


def _build_provider_model_string(provider: str, model: str) -> str:
    provider_prefixes = {
        "vertexai": "vertex_ai",
        "vertex_ai": "vertex_ai",
        "gemini": "gemini",
        "openai": "openai",
        "anthropic": "anthropic",
    }
    prefix = provider_prefixes.get(provider)
    if prefix is None:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    return f"{prefix}/{model}"


def _create_instructor_client(provider: str, model: str) -> Any:
    """Create an Instructor-patched client for the configured provider."""
    import instructor

    if provider in ("openai",):
        from openai import OpenAI

        return instructor.from_openai(OpenAI()), model
    if provider in ("vertexai", "vertex_ai"):
        from openai import OpenAI

        return instructor.from_openai(OpenAI()), _build_provider_model_string(provider, model)
    if provider == "gemini":
        from openai import OpenAI

        return instructor.from_openai(OpenAI()), _build_provider_model_string(provider, model)
    if provider == "anthropic":
        try:
            from anthropic import Anthropic

            return instructor.from_anthropic(Anthropic()), model
        except ImportError:
            raise ValueError("anthropic package required for Anthropic provider")

    raise ValueError(f"Unsupported LLM provider for Instructor: {provider}")


class InstructorMetadataExtractor:
    """MetadataExtractor using Instructor + Pydantic for schema-validated LLM calls.

    Satisfies the ``MetadataExtractor`` protocol from
    ``document_intelligence.extractors.metadata``.
    """

    def __init__(
        self,
        profile: ExtractionProfileConfig | None = None,
    ) -> None:
        self._profile = profile or ExtractionProfileConfig.from_environment()
        self._client, self._model = _create_instructor_client(self._profile.llm_provider, self._profile.llm_model)

    def extract(
        self,
        *,
        normalized_document: NormalizedDocumentIR,
        manifest: ArtifactBundleManifest,
        primary_artifact: ArtifactBundleManifestArtifact,
    ) -> MetadataExtractionCandidate | None:
        import json as json_mod

        hints = gather_metadata_hints_for_llm(manifest, primary_artifact)
        body = normalized_document.full_text[:_MAX_BODY_CHARS]
        hints_str = json_mod.dumps(hints, default=str, ensure_ascii=False)[:2000]

        raw: dict[str, Any] = {
            "profile": {
                "provider": self._profile.llm_provider,
                "model": self._profile.llm_model,
            }
        }

        title: str | None = None
        document_type: str | None = None
        confidence = 0.0

        try:
            result: LegalDocumentMetadata = self._client.chat.completions.create(
                model=self._model,
                response_model=LegalDocumentMetadata,
                max_retries=2,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Document text (first {_MAX_BODY_CHARS} chars):\n\n{body}\n\nMetadata hints:\n{hints_str}"
                        ),
                    },
                ],
            )
            title = result.title
            document_type = result.source_family
            if document_type == "unknown":
                document_type = None
            confidence = result.confidence
            raw["extraction"] = result.model_dump()
        except Exception:
            logger.exception("Instructor metadata extraction failed")
            raw["extraction"] = {"error": "extractor_failed"}

        if self._profile.enable_commentary_extractor and document_type == "commentary":
            try:
                commentary = self._client.chat.completions.create(
                    model=self._model,
                    response_model=CommentaryPassages,
                    max_retries=1,
                    messages=[
                        {
                            "role": "system",
                            "content": "Extract key commentary passages and referenced legal provisions.",
                        },
                        {"role": "user", "content": body},
                    ],
                )
                raw["commentary_passages"] = commentary.model_dump()
            except Exception:
                logger.exception("Commentary extraction failed")
                raw["commentary_passages"] = {"error": "extractor_failed"}

        return MetadataExtractionCandidate(
            title=title,
            document_type=document_type,
            confidence=confidence,
            model=self._profile.llm_model,
            provider=self._profile.llm_provider,
            raw=raw,
        )
