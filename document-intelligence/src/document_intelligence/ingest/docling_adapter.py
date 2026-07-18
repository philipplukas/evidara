"""Docling parser adapter with deterministic fallback behavior.

Two entry points, one per modality:

- :func:`normalize_with_docling` — text artifacts (HTML/XML/plain), the original path.
- :func:`normalize_pdf_with_docling` — PDF **bytes** (ADR-0038). A PDF cannot be routed
  through the text entry point at all: it takes ``artifact_text: str``, and decoding PDF
  bytes to text destroys the document. That structural gap is why ``DI_PARSER_BACKEND=docling``
  used to still yield pdfplumber output for every PDF.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from document_intelligence.errors import ProcessingError
from document_intelligence.normalize.html import (
    normalize_html_document,
    normalize_plain_text_document,
)
from document_intelligence.normalize.ir import Block, NormalizedDocumentIR
from document_intelligence.normalize.marginalia import (
    detect_marginal_blocks,
    lift_marginal_headings,
)
from document_intelligence.normalize.xml import normalize_xml_document


def _is_placeholder_title(title: str | None) -> bool:
    if title is None:
        return True
    normalized = title.strip()
    if not normalized:
        return True
    lowered = normalized.lower()
    if lowered in {"untitled document", "ris dokument"}:
        return True
    # Normalize whitespace + dashes for RIS placeholder variants
    # ("RIS — Dokument", "RIS – Dokument", "RIS - Dokument", "RIS  -  Dokument")
    collapsed = " ".join(lowered.split())
    ris_normalized = collapsed.replace("\u2014", "-").replace("\u2013", "-")
    if ris_normalized.startswith("ris -") or ris_normalized.startswith("ris-"):
        return True
    return False


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


def normalize_pdf_with_docling(*, artifact_id: str, pdf_bytes: bytes) -> NormalizedDocumentIR:
    """Normalize a PDF byte payload through docling, then lift marginal headings.

    Raises :class:`ProcessingError` when docling is unavailable or the conversion yields
    nothing usable. Callers decide whether to fall back — this function never silently
    degrades to a weaker extractor, because the weaker extractor is precisely what
    corrupts this document class (ADR-0038).
    """
    try:
        converter = _pdf_converter()
    except ImportError as error:  # pragma: no cover - exercised only without docling
        raise ProcessingError(
            "missing_pdf_dependency",
            "docling is required to normalise application/pdf artifacts; it is a core "
            "document-intelligence dependency (see docs/adr/0038).",
        ) from error

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        temp_file.write(pdf_bytes)
        temp_path = Path(temp_file.name)

    try:
        result = converter.convert(str(temp_path))
    except Exception as error:
        raise ProcessingError("pdf_conversion_failed", f"docling could not convert the PDF: {error}") from error
    finally:
        temp_path.unlink(missing_ok=True)

    doc = result.document
    page_count = len(getattr(doc, "pages", ()) or ())
    blocks = _pdf_blocks(doc, artifact_id=artifact_id)

    metadata: dict[str, Any] = {
        "title": None,
        "language": None,
        "normalizer": "pdf_docling_v1",
        "source_profile_ref": "default_pdf_v1",
        "normalization_profile_ref": "pdf_docling_v1",
        "source_flavor": "layout_pdf",
        "pdf_page_count": page_count,
        "pdf_extractor": "docling",
        "pdf_layout_aware": True,
        "docling": {"enabled": True, "backend": "docling", "content_type": "application/pdf"},
    }

    if not blocks:
        # No text layer at all: an honest empty IR flagged for OCR beats fabricated body
        # text. Unchanged from ADR-0037's contract.
        metadata["pdf_no_text_layer"] = True
        return NormalizedDocumentIR(blocks=[], metadata=metadata)

    ir, diagnostics = lift_marginal_headings(
        NormalizedDocumentIR(blocks=blocks, metadata=metadata),
        _safe_detect_marginal_blocks(pdf_bytes),
    )
    metadata = dict(ir.metadata)
    metadata["pdf_marginalia"] = diagnostics
    for block in ir.blocks:
        if block.type == "heading" and block.text.strip():
            metadata["title"] = block.text.strip()
            break
    return NormalizedDocumentIR(blocks=list(ir.blocks), metadata=metadata)


def _pdf_converter() -> Any:
    """Build the PDF converter with OCR explicitly disabled.

    OCR stays out of scope (ADR-0037 deferred it, ADR-0038 keeps it deferred): an
    image-only PDF yields an empty IR flagged ``pdf_no_text_layer`` for a future OCR pass
    rather than being guessed at. Turning it off here is also what keeps the runtime image
    lean — docling's OCR engine pulls opencv, which needs system libraries
    (``libgl1``, ``libglib2.0-0``, ``libxcb1``) that ``python:3.12-slim`` does not ship.

    To enable OCR later: install those libs in the image, add ``with_rapidocr=True`` to the
    model bake, and flip ``do_ocr``. Leaving the default (``do_ocr=True``) with the engine
    absent is the one thing that must not happen — docling then raises mid-conversion and
    the caller silently falls back to the splicing extractor.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False
    # Layout analysis is the whole point — it is what keeps the Randtitel out of the
    # sentence — so it stays on. Table structure is cheap and legal PDFs carry fee tables.
    options.do_table_structure = True
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def _safe_detect_marginal_blocks(pdf_bytes: bytes) -> list[Any]:
    """Marginalia detection is an enhancement, not a correctness precondition.

    If the geometry pass fails we still return docling's text — which already keeps the
    body sentence intact. Only the *placement* of the Randtitel degrades.
    """
    try:
        return list(detect_marginal_blocks(pdf_bytes))
    except Exception:
        return []


def _pdf_blocks(doc: Any, *, artifact_id: str) -> list[Block]:
    """Map docling items to IR blocks, carrying the page geometry the lift pass needs."""
    blocks: list[Block] = []
    for order, (item, _tree_level) in enumerate(doc.iterate_items()):
        text = " ".join(str(getattr(item, "text", "") or "").split())
        if not text or text == "<unknown>":
            continue
        label = str(getattr(getattr(item, "label", None), "value", getattr(item, "label", "")) or "")
        level = _item_level(item)
        if label == "section_header":
            block_type, level = "heading", level or 1
        elif label == "list_item":
            block_type = "list_item"
        else:
            block_type = "heading" if level is not None else "paragraph"

        attrs: dict[str, Any] = {"source": "docling", "tag": "pdf"}
        if label:
            attrs["docling_label"] = label
        page_no, top, bottom = _item_geometry(item, doc)
        if page_no is not None:
            attrs["page_no"] = page_no
            attrs["bbox_top"] = top
            attrs["bbox_bottom"] = bottom

        blocks.append(
            Block(
                id=f"blk_{order:04d}",
                type=block_type,
                text=text,
                level=level,
                order=order,
                artifact_id=artifact_id,
                attrs=attrs,
            )
        )
    return blocks


def _item_geometry(item: Any, doc: Any) -> tuple[int | None, float | None, float | None]:
    """Return (page_no, top, bottom) in **top-origin** page coordinates.

    Docling reports bounding boxes bottom-left-origin; the marginalia pass works in
    pdfplumber's top-origin space, so this is where the two conventions are reconciled.
    """
    provs = getattr(item, "prov", None) or []
    if not provs:
        return None, None, None
    page_no = getattr(provs[0], "page_no", None)
    if page_no is None:
        return None, None, None

    page = (getattr(doc, "pages", {}) or {}).get(page_no)
    height = getattr(getattr(page, "size", None), "height", None)
    if height is None:
        return page_no, None, None

    tops: list[float] = []
    bottoms: list[float] = []
    for prov in provs:
        if getattr(prov, "page_no", None) != page_no:
            continue
        bbox = getattr(prov, "bbox", None)
        if bbox is None:
            continue
        tops.append(float(height) - float(bbox.t))
        bottoms.append(float(height) - float(bbox.b))
    if not tops:
        return page_no, None, None
    return page_no, min(tops), max(bottoms)


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
) -> tuple[list[Block], str] | None:
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
        title = (getattr(doc, "name", "") or "").strip()
        placeholder = _is_placeholder_title(title)
        if placeholder:
            title = "Untitled document"
        blocks: list[Block] = []
        # ``iterate_items`` yields ``(item, tree_level)`` pairs, not bare items. Unpacking
        # it as a single value made ``_item_text`` return "" for every node, so this
        # function always produced zero blocks and silently fell back to the legacy
        # normaliser — i.e. the docling backend had never actually run (ADR-0038).
        for order, (item, _tree_level) in enumerate(doc.iterate_items()):
            text = _item_text(item)
            if not text:
                continue
            level = _item_level(item)
            block_type = "heading" if level is not None else "paragraph"
            blocks.append(
                Block(
                    id=f"docling_{artifact_id}_{order}",
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
        # When the HTML <title> was a placeholder (e.g. "RIS Dokument"),
        # prefer the first heading in the body as the document title.
        if placeholder:
            for block in blocks:
                if block.type == "heading" and block.text.strip():
                    heading = block.text.strip()
                    if not _is_placeholder_title(heading):
                        title = heading
                        break
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
