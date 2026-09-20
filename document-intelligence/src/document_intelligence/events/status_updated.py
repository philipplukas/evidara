"""Outbound processing status event construction, and who writes each status.

A status declared in the contract enum and written by nobody is worse than a status
that does not exist: every reader of the ledger sees a zero and reads it as *this
never happened*. That is how `/v1/coverage`'s `quarantined_documents` sat at a
structural zero from #731 until #1045 — declared on three surfaces, counted per
jurisdiction, and emitted by no call site.

`STATUS_PRODUCERS` is the answer to "who writes this", kept beside the builder that
writes most of them. It is not documentation: `tests/test_status_producers.py` reads
the contract enum, requires an entry for every member, and — for the statuses claimed
by this package — proves the claim by running the pipeline and collecting what it
actually emitted.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from document_intelligence.canonical.ids import random_prefixed_id
from document_intelligence.contracts.envelope import Provenance

#: Component identifiers used by :data:`STATUS_PRODUCERS`.
DOCUMENT_INTELLIGENCE = "document-intelligence"
PLATFORM_CONTROL = "platform-control"


@dataclass(frozen=True, slots=True)
class StatusProducer:
    """Who emits one processing status, or the fact that nobody does.

    ``component`` is ``None`` exactly when the status has no writer anywhere in the
    estate. That is a defect, not a configuration: ``where`` must then name the issue
    tracking it, so the gap is carried in the code that declares it rather than
    rediscovered from a permanently-zero counter months later.
    """

    component: str | None
    where: str

    @property
    def exists(self) -> bool:
        return self.component is not None


#: Every status in `contracts/events/document-processing-status-updated.schema.json`,
#: mapped to the thing that writes it.
#:
#: `failed` is platform-control's and only platform-control's: the reclaim sweep
#: (#1042) writes it on a deadline, and its summary says so in words, because the
#: control plane stopped waiting is not the same claim as document-intelligence
#: reported a failure.
STATUS_PRODUCERS: dict[str, StatusProducer] = {
    "accepted": StatusProducer(
        DOCUMENT_INTELLIGENCE,
        "ProcessingPipeline.process_event — built before normalisation, persisted at either ending",
    ),
    "processing": StatusProducer(
        DOCUMENT_INTELLIGENCE,
        "ProcessingPipeline.process_event — built beside `accepted`",
    ),
    "canonical_ready": StatusProducer(
        DOCUMENT_INTELLIGENCE,
        "ProcessingPipeline.process_event — the `finalize` stage, success ending",
    ),
    "quarantined": StatusProducer(
        DOCUMENT_INTELLIGENCE,
        "ProcessingPipeline._quarantine_result — the ADR-0047 refusal ending (#1045)",
    ),
    "failed": StatusProducer(
        PLATFORM_CONTROL,
        "ProcessingReclaimService.reclaim_stranded_units — on a deadline, never on DI's word (#1042)",
    ),
    "withdrawn": StatusProducer(
        None,
        "nothing emits this; document withdrawal is published as `document.withdrawn` "
        "and never as a processing status — tracked by #1045",
    ),
    "skipped_duplicate": StatusProducer(
        None,
        "nothing emits this; the pipeline has no duplicate-suppression ending — tracked by #1045",
    ),
}

#: The statuses this package claims to emit. Derived from the registry rather than
#: re-listed, so the two cannot disagree.
DOCUMENT_INTELLIGENCE_STATUSES = frozenset(
    status for status, producer in STATUS_PRODUCERS.items() if producer.component == DOCUMENT_INTELLIGENCE
)


def build_processing_status_event(
    *,
    processing_manifest_id: str,
    provenance: Provenance,
    processing_version: str,
    status: str,
    document_id: str | None,
    document_revision: int | None,
    correlation_id: str | None,
    causation_id: str | None,
    error_code: str | None = None,
    error_summary: str | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "document.processing_status.updated",
        "event_version": 1,
        "event_id": random_prefixed_id("evt"),
        "occurred_at": _utc_now(),
        "producer": "document-intelligence",
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "payload": {
            "processing_manifest_id": processing_manifest_id,
            "document_id": document_id,
            "document_revision": document_revision,
            "provenance": provenance.to_dict(),
            "processing_version": processing_version,
            "status": status,
            "error_code": error_code,
            "error_summary": error_summary,
        },
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
