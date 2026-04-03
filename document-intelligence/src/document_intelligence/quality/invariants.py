"""Invariant checks for canonical processing output."""

from collections.abc import Iterable

from document_intelligence.canonical.models import Document, Section


def validate_document_and_sections(document: Document, sections: Iterable[Section]) -> None:
    if not document.title:
        raise ValueError("document title must be populated")
    if not document.processed_at:
        raise ValueError("document processed_at must be populated")

    previous_ordinal = -1
    for section in sections:
        if section.document_id != document.document_id:
            raise ValueError("section document_id must match parent document")
        if section.document_revision != document.document_revision:
            raise ValueError("section document_revision must match parent document")
        if section.processing_manifest_id != document.processing_manifest_id:
            raise ValueError("section processing_manifest_id must match parent document")
        if section.provenance.document_id != document.document_id:
            raise ValueError("section provenance document_id must match parent document")
        if section.ordinal <= previous_ordinal:
            raise ValueError("section ordinals must be strictly increasing")
        previous_ordinal = section.ordinal
