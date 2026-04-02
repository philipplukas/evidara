"""Derive lean Docling JSON and plain text from a stored document payload.

Preferred path: parse with ``docling_core`` and use ``DoclingDocument.export_to_dict`` /
``export_to_text`` (see Docling serialization docs). On ``ImportError`` or validation
failure, fall back to heuristic dict walking so file-backed dev fixtures still work.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Common layout-only keys to drop after ``export_to_dict`` (and for heuristic fallback).
_LAYOUT_KEYS = frozenset(
    {
        "bbox",
        "bounding_box",
        "confidence",
        "l2b_bbox",
        "prov",
        "image",
        "cells_bbox",
    }
)


def strip_layout_fields(obj: Any) -> Any:
    """Recursively remove layout-oriented keys from dict/list structures."""
    if isinstance(obj, dict):
        return {
            k: strip_layout_fields(v)
            for k, v in obj.items()
            if k not in _LAYOUT_KEYS and not k.endswith("_bbox")
        }
    if isinstance(obj, list):
        return [strip_layout_fields(x) for x in obj]
    return obj


def extract_plain_text(obj: Any) -> str:
    """Collect strings from arbitrary JSON (fallback when Docling parse fails)."""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            s = node.strip()
            if s:
                parts.append(s)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return "\n\n".join(parts)


def _load_docling_document(body: dict[str, Any]) -> Any | None:
    """Return a ``DoclingDocument`` instance or ``None`` if unavailable / invalid."""
    try:
        from docling_core.types.doc.document import DoclingDocument
    except ImportError:
        return None
    try:
        return DoclingDocument.model_validate(body)
    except Exception as exc:
        logger.debug("DoclingDocument.model_validate failed, using fallback: %s", exc)
        return None


def to_lean_dict(body: dict[str, Any]) -> dict[str, Any]:
    """
    Lean Docling-shaped JSON for ``GET .../lean``.

    Uses ``export_to_dict`` with compacted coordinates/confidence when parse succeeds,
    then applies :func:`strip_layout_fields` for any remaining layout keys.
    """
    doc = _load_docling_document(body)
    if doc is not None:
        exported = doc.export_to_dict(coord_precision=0, confid_precision=0)
        return strip_layout_fields(exported)
    return strip_layout_fields(body)


def to_plain_text(body: dict[str, Any]) -> str:
    """
    Plain text for ``GET .../text``.

    Uses Docling's ``export_to_text`` when parse succeeds; otherwise
    :func:`extract_plain_text`.
    """
    doc = _load_docling_document(body)
    if doc is not None:
        return doc.export_to_text()
    return extract_plain_text(body)
