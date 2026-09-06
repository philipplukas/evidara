"""Per-stage record of what one document's processing actually did.

The pipeline's whole run was previously observable as three status transitions —
``accepted`` → ``processing`` → one of ``canonical_ready`` / ``failed`` /
``quarantined`` — plus three Prometheus counters that are aggregate, not
per-document. So "where did the time go" and "which stage dropped it" were not
answerable for any individual document, on any surface. This records them.

**Scope, deliberately.** Entries carry timings and in/out counts only. They do
NOT yet carry what a stage *removed* from the text — footnote apparatus, page
furniture, a lifted Randtitel, a dropped citation. That disclosure is ADR-0044's
subject and needs a per-stage vocabulary this module does not invent. The shape
here leaves room for it (a stage entry is a mapping, and the schema permits
future keys under ``details``) without pretending to provide it: an operator
reading a stage row must not conclude that "nothing was removed" merely because
removals are not listed.

**A stage that raises still gets an entry.** ``failed=True`` with the exception
type, recorded before the exception propagates. A ledger that only describes
successful runs is worse than none: it would be systematically absent for exactly
the documents someone is trying to debug.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

#: The pipeline's stage vocabulary, in execution order.
#:
#: Closed on purpose. A free-form stage name would let two call sites disagree
#: about what "extract" means and make the ledger unaggregatable across
#: documents. Adding a stage is a deliberate edit here plus a schema bump.
#:
#: The names describe where the work actually happens in ``process_event``, not a
#: tidier pipeline someone might wish for: ``assemble`` sits between ``extract``
#: and ``enrich`` because ``_build_document`` genuinely runs there — enrichment
#: mutates a document that must already exist.
#:
#: There is deliberately no ``persist`` stage. The ledger is carried *by* the
#: processing manifest, and the manifest is what persistence writes: a stage
#: covering the write cannot appear inside the thing being written. Declaring one
#: anyway would put a row in the vocabulary that no producer can ever fill, which
#: reads to an operator as "persistence never ran". Sink timing belongs to the
#: sink, and is a separate measurement.
STAGE_NAMES: tuple[str, ...] = (
    "normalize",
    "sectionize",
    "extract",
    "assemble",
    "enrich",
    "finalize",
)


class UnknownStageError(ValueError):
    """Raised when a stage name is not in ``STAGE_NAMES``.

    Loud on purpose: a typo'd stage name would otherwise produce a ledger entry
    nothing aggregates, which reads downstream as "that stage never ran".
    """


@dataclass
class StageEntry:
    name: str
    duration_ms: int
    items_in: int | None = None
    items_out: int | None = None
    failed: bool = False
    error_type: str | None = None
    #: Reserved for ADR-0044 transformation disclosure. Empty today, and its
    #: emptiness means "not recorded", never "nothing happened".
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        output: dict[str, Any] = {"name": self.name, "duration_ms": self.duration_ms}
        if self.items_in is not None:
            output["items_in"] = self.items_in
        if self.items_out is not None:
            output["items_out"] = self.items_out
        if self.failed:
            output["failed"] = True
        if self.error_type is not None:
            output["error_type"] = self.error_type
        if self.details:
            output["details"] = dict(self.details)
        return output


class StageLedger:
    """Collects :class:`StageEntry` values for one document's processing.

    Not thread-safe and not meant to be: one ledger belongs to one
    ``process_event`` call, which is single-threaded.
    """

    def __init__(self) -> None:
        self._entries: list[StageEntry] = []

    @contextmanager
    def stage(
        self,
        name: str,
        *,
        items_in: int | None = None,
    ) -> Iterator[StageEntry]:
        """Time a stage and append its entry.

        The yielded entry is mutable so the caller can set ``items_out`` once it
        knows it::

            with ledger.stage("sectionize", items_in=1) as entry:
                sections = build_sections(...)
                entry.items_out = len(sections)

        On an exception the entry is still appended, marked ``failed`` with the
        exception's type name, and the exception re-raised untouched.
        """
        if name not in STAGE_NAMES:
            raise UnknownStageError(f"Unknown pipeline stage {name!r}. Known stages: {', '.join(STAGE_NAMES)}.")
        entry = StageEntry(name=name, duration_ms=0, items_in=items_in)
        started = time.perf_counter()
        try:
            yield entry
        except BaseException as exc:
            entry.duration_ms = _elapsed_ms(started)
            entry.failed = True
            entry.error_type = type(exc).__name__
            self._entries.append(entry)
            raise
        entry.duration_ms = _elapsed_ms(started)
        self._entries.append(entry)

    @property
    def entries(self) -> list[StageEntry]:
        return list(self._entries)

    def to_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]

    def total_duration_ms(self) -> int:
        return sum(entry.duration_ms for entry in self._entries)


def _elapsed_ms(started: float) -> int:
    """Elapsed milliseconds, floored at 0.

    ``perf_counter`` is monotonic, so a negative value is impossible; the floor
    guards against a 0-duration stage rendering as a missing measurement.
    """
    return max(0, int((time.perf_counter() - started) * 1000))
