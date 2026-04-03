"""Docling parser adapter with deterministic fallback behavior."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, List, Tuple

from document_intelligence.normalize.html import (
    normalize_html_document,
    normalize_plain_text_document,
)
from document_intelligence.normalize.ir import Block, NormalizedDocumentIR
from document_intelligence.normalize.xml import normalize_xml_document


def normalize_with_docling(
    *,
    artifact_id: str,
    artifact_text: str,
    content_type: str,
) -> NormalizedDocumentIR:
    """Use Docling conversion where available and safe."""
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    converted = _convert_with_docling(
        artifact_id=artifact_id,
        artifact_text=artifact_text,
        content_type=normalized_content_type,
    )
    if converted is not None:
        blocks, title = converted
        return NormalizedDocumentIR(
            blocks=blocks,
            metadata={
                "title": title,
                "normalizer": "docling_v1",
                "normalization_profile_ref": "docling_v1",
                "docling": {
                    "enabled": True,
                    "backend": "docling",
                    "content_type": normalized_content_type,
                },
            },
        )

    normalized = _fallback_normalize(
        artifact_id=artifact_id,
        artifact_text=artifact_text,
        content_type=normalized_content_type,
    )
    metadata = dict(normalized.metadata)
    metadata["normalization_profile_ref"] = "docling_fallback_v1"
    metadata["normalizer"] = "docling_fallback_v1"
    metadata["docling"] = {
        "enabled": True,
        "backend": "fallback",
        "content_type": normalized_content_type,
    }
    return NormalizedDocumentIR(blocks=list(normalized.blocks), metadata=metadata)


def _fallback_normalize(
    *,
    artifact_id: str,
    artifact_text: str,
    content_type: str,
) -> NormalizedDocumentIR:
    if content_type in {"text/html", "application/xhtml+xml"}:
        return normalize_html_document(artifact_text, artifact_id)
    if content_type in {"application/xml", "text/xml"}:
        return normalize_xml_document(artifact_text, artifact_id)
    if content_type.startswith("text/plain"):
        return normalize_plain_text_document(artifact_text, artifact_id)
    # Keep unsupported modality behavior aligned with the legacy path.
    return normalize_plain_text_document(artifact_text, artifact_id)


def _convert_with_docling(
    *,
    artifact_id: str,
    artifact_text: str,
    content_type: str,
) -> Tuple[List[Block], str] | None:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        return None

    suffix = _content_type_suffix(content_type)
    if suffix is None:
        return None

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=suffix,
        delete=False,
    ) as temp_file:
        temp_file.write(artifact_text)
        temp_path = Path(temp_file.name)

    try:
        converter = DocumentConverter()
        conversion_result = converter.convert(str(temp_path))
        doc = conversion_result.document
        title = (getattr(doc, "name", "") or "").strip() or "Untitled document"
        blocks: List[Block] = []
        for order, item in enumerate(doc.iterate_items()):
            text = _item_text(item)
            if not text:
                continue
            level = _item_level(item)
            block_type = "heading" if level is not None else "paragraph"
            blocks.append(
                Block(
                    id="docling_{artifact}_{idx}".format(artifact=artifact_id, idx=order),
                    type=block_type,
                    text=text,
                    order=order,
                    artifact_id=artifact_id,
                    level=level,
                    attrs={"source": "docling"},
                )
            )

        if not blocks:
            return None
        return blocks, title
    except Exception:
        return None
    finally:
        temp_path.unlink(missing_ok=True)


def _content_type_suffix(content_type: str) -> str | None:
    if content_type in {"text/html", "application/xhtml+xml"}:
        return ".html"
    if content_type in {"application/xml", "text/xml"}:
        return ".xml"
    if content_type.startswith("text/plain"):
        return ".txt"
    return None


def _item_text(item: Any) -> str:
    if hasattr(item, "export_to_markdown"):
        exported = item.export_to_markdown()
        if isinstance(exported, str) and exported.strip():
            return exported.strip()
    text = getattr(item, "text", None)
    if isinstance(text, str):
        return text.strip()
    return ""


def _item_level(item: Any) -> int | None:
    value = getattr(item, "level", None)
    if isinstance(value, int):
        return max(1, value)
    return None
