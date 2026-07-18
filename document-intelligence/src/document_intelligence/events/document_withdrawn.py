"""Outbound ``document.withdrawn`` event construction.

Used by the projection reconcile job (ADR-0005) to de-index a search projection whose
canonical ``published_documents`` row no longer exists. The de-index primitive itself
already lives in legal-search — ``applyDocumentWithdrawn`` deletes the projection, its
sections and its citations — so reconciliation reuses that path instead of introducing a
second, differently-behaved delete.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from document_intelligence.canonical.ids import random_prefixed_id
from document_intelligence.errors import ProcessingError

# A search projection stores `source_id` / `source_version_id` / `run_id` but NOT
# tenant/corpus/scope, so those three cannot be recovered from the index row. They are
# required by `contracts/common/provenance.schema.json` and pattern-constrained, so the
# event carries explicitly-unknown values rather than plausible-looking invented ones.
#
# This is safe because nothing reads them: legal-search's `applyDocumentWithdrawn` uses
# only `document_id` and `document_revision`, and the projection-history row it appends
# keeps `run_id` (which IS accurate, read off the index). The reconcile job POSTs straight
# to legal-search rather than publishing on NATS, so platform-control — the other
# `document.withdrawn` consumer — never sees these values either.
_UNKNOWN_TENANT_ID = "tenant_unknown_not_stored_on_projection"
_UNKNOWN_CORPUS_ID = "corpus_unknown_not_stored_on_projection"
# `scope_type` is a closed enum with no "unknown" member. `global_public` is the honest
# choice, not a filler: anything reachable in the public search index is public by
# construction.
_SCOPE_TYPE = "global_public"


def build_document_withdrawn_event_from_indexed_row(
    row: Mapping[str, Any],
    *,
    reason_summary: str,
    reason_code: str = "operator_withdrawn",
) -> dict[str, Any]:
    """Build a contract-valid ``document.withdrawn`` event from an indexed projection row.

    The row comes from legal-search's ``GET /v1/projections/documents``, which echoes
    back the ids the originating ``document.processed`` event carried. Those ids are
    therefore read off the index rather than invented — a row that does not carry them
    cannot produce a valid withdrawal, and this raises :class:`ProcessingError` so the
    reconcile job records it as unwithdrawable instead of guessing.

    ``search_disposition`` is always ``remove``: an orphan has no canonical row to keep
    it auditable against, so hiding it would leave unreachable data in the index forever.
    """
    document_id = _required_id(row, "document_id", "doc_")
    revision = row.get("document_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ProcessingError(
            "reconcile_row_unwithdrawable",
            f"indexed document {document_id} has invalid document_revision {revision!r}",
        )

    payload: dict[str, Any] = {
        "document_id": document_id,
        "document_revision": revision,
        "processing_manifest_id": _required_id(row, "processing_manifest_id", "pm_"),
        "provenance": {
            "tenant_id": _UNKNOWN_TENANT_ID,
            "corpus_id": _UNKNOWN_CORPUS_ID,
            "scope_type": _SCOPE_TYPE,
            "source_id": _required_id(row, "source_id", "src_"),
            "source_version_id": _required_id(row, "source_version_id", "sv_"),
            "run_id": _required_id(row, "run_id", "run_"),
        },
        "reason_code": reason_code,
        "reason_summary": reason_summary,
        "search_disposition": "remove",
    }

    return {
        "event_type": "document.withdrawn",
        "event_version": 1,
        # A fresh event id per emission: a surviving projection-history index must never
        # short-circuit a withdrawal as an already-seen duplicate.
        "event_id": random_prefixed_id("evt"),
        "occurred_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "producer": "document-intelligence",
        "correlation_id": payload["provenance"]["run_id"],
        "payload": payload,
    }


def _required_id(row: Mapping[str, Any], field_name: str, prefix: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip().startswith(prefix):
        raise ProcessingError(
            "reconcile_row_unwithdrawable",
            f"indexed row is missing a usable {field_name} (got {value!r})",
        )
    return value.strip()


__all__ = ["build_document_withdrawn_event_from_indexed_row"]
