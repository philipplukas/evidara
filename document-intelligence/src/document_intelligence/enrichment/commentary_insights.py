"""Extractive commentary insight generation.

The MVP intentionally emits only source-backed anchors. It does not generate
legal analysis or prose that is absent from the source document.
"""

from __future__ import annotations

from document_intelligence.canonical.ids import stable_prefixed_id
from document_intelligence.canonical.models import CommentaryInsight, Document, Section
from document_intelligence.nlp.citation_extractor import Citation, extract_citations, normalize_citation

_GENERATOR_NAME = "commentary-insight-extractor"
_GENERATOR_VERSION = "v1"


def extract_commentary_insights(
    *,
    document: Document,
    sections: list[Section],
    min_confidence: float = 0.7,
) -> list[CommentaryInsight]:
    """Extract source-backed commentary anchors from section text."""
    insights: list[CommentaryInsight] = []
    seen_passages: set[tuple[str, str]] = set()

    for section in sorted(sections, key=lambda item: item.ordinal):
        for passage_index, passage in enumerate(_iter_candidate_passages(section.content)):
            citations = extract_citations(passage)
            if not citations:
                continue
            if passage not in section.content:
                continue

            key = (section.section_id, passage)
            if key in seen_passages:
                continue
            seen_passages.add(key)

            authorities = [_authority_from_citation(citation) for citation in citations]
            confidence = _confidence_for(citations, authorities)
            if confidence < min_confidence:
                continue

            insight_type = _insight_type_for(citations)
            insight = CommentaryInsight(
                insight_id=stable_prefixed_id(
                    "ins",
                    document.document_id,
                    document.processing_manifest_id,
                    section.section_id,
                    str(passage_index),
                    "|".join(citation.text for citation in citations),
                ),
                document_id=document.document_id,
                document_revision=document.document_revision,
                processing_manifest_id=document.processing_manifest_id,
                section_id=section.section_id,
                citation_id=None,
                insight_type=insight_type,
                claim=_claim_for(citations, authorities),
                display_text=passage,
                support=[
                    {
                        "document_id": document.document_id,
                        "section_id": section.section_id,
                        "citation_id": None,
                        "ref_type": "passage",
                        "passage": passage,
                        "confidence": confidence,
                        "metadata": {"source": f"{_GENERATOR_NAME}-{_GENERATOR_VERSION}"},
                    }
                ],
                referenced_authorities=authorities,
                language=_document_language(document),
                jurisdiction_id=document.jurisdiction_id,
                confidence=confidence,
                review_state="machine_verified",
                generator={
                    "name": _GENERATOR_NAME,
                    "version": _GENERATOR_VERSION,
                    "model": None,
                    "prompt_version": None,
                },
                scores={
                    "passage_present": 1.0,
                    "citation_parseable": 1.0,
                    "section_anchor_resolved": 1.0,
                },
                metadata={"extractive": True},
            )
            insights.append(insight)

    return insights


def _iter_candidate_passages(content: str) -> list[str]:
    passages: list[str] = []
    current: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                passages.append(" ".join(current))
                current = []
            continue
        current.append(line)
    if current:
        passages.append(" ".join(current))

    if len(passages) == 1:
        return _split_long_passage(passages[0])
    return [passage for passage in passages if passage]


def _split_long_passage(passage: str, *, max_chars: int = 900) -> list[str]:
    if len(passage) <= max_chars:
        return [passage]
    sentences = []
    start = 0
    for idx, char in enumerate(passage):
        if char in {".", "!", "?"} and idx + 1 < len(passage) and passage[idx + 1].isspace():
            candidate = passage[start : idx + 1].strip()
            if candidate:
                sentences.append(candidate)
            start = idx + 1
    tail = passage[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences or [passage[:max_chars].strip()]


def _authority_from_citation(citation: Citation) -> dict[str, object]:
    authority: dict[str, object] = {
        "text": citation.text,
        "citation_type": citation.citation_type,
    }
    normalized = normalize_citation(citation)
    if normalized:
        authority["normalized_reference"] = normalized
    authority["metadata"] = dict(citation.metadata)
    return authority


def _confidence_for(citations: list[Citation], authorities: list[dict[str, object]]) -> float:
    if any(authority.get("normalized_reference") for authority in authorities):
        return 0.95
    if citations:
        return 0.78
    return 0.0


def _claim_for(citations: list[Citation], authorities: list[dict[str, object]]) -> str:
    normalized = next(
        (authority.get("normalized_reference") for authority in authorities if authority.get("normalized_reference")),
        None,
    )
    if isinstance(normalized, str):
        return f"References {normalized}"
    first = citations[0].text if citations else "commentary passage"
    return f"References {first}"


def _insight_type_for(citations: list[Citation]) -> str:
    provision_types = {
        "sr",
        "article",
        "de_paragraph",
        "fr_code_article",
        "it_codice_article",
        "eu_regulation",
        "eu_directive",
        "eu_celex",
    }
    if any(citation.citation_type in provision_types for citation in citations):
        return "referenced_provision"
    authority_types = {
        "bge",
        "eu_ecli",
        "de_ecli",
        "fr_ecli",
        "it_ecli",
        "de_bverfge",
        "de_bverfg_docket",
        "de_bgh",
        "fr_pourvoi",
        "fr_cassation",
        "fr_conseil_etat",
        "it_cassazione",
        "it_consiglio_stato",
    }
    if any(citation.citation_type in authority_types for citation in citations):
        return "authority_link"
    return "commentary_anchor"


def _document_language(document: Document) -> str | None:
    original_language = document.metadata.get("original_language")
    if isinstance(original_language, str) and original_language.strip():
        return original_language.strip().split("-")[0].lower()
    source_defaults = document.metadata.get("source_defaults")
    if isinstance(source_defaults, dict):
        languages = source_defaults.get("language_codes")
        if isinstance(languages, list):
            for candidate in languages:
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip().split("-")[0].lower()
    return None
