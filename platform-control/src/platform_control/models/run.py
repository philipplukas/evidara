from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import RunMode, RunStatus
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin, utcnow

#: `run_metadata` key recording that a run's captured documents were deliberately
#: never published (#853), and the companion key holding how many artifacts really
#: reached the broker. Both are read back through the helpers below rather than
#: inline, because `RunService.list_runs` selects columns instead of entities and
#: would otherwise re-implement the reading.
DISPATCH_PUBLISH_WITHHELD_KEY = "dispatch_publish_withheld"
PUBLISHED_ARTIFACTS_COUNT_KEY = "published_artifacts_count"


def publication_withheld_from(run_metadata: dict[str, Any] | None) -> bool:
    return (run_metadata or {}).get(DISPATCH_PUBLISH_WITHHELD_KEY) is True


def published_artifacts_count_from(
    run_metadata: dict[str, Any] | None, artifacts_count: int
) -> int:
    """How many artifacts left the service, defaulting to "all of them".

    Only the two paths that publish less than they captured — the #853 withhold and
    the #707 partial handoff — write the key. Every other run published what it
    captured, so an absent key must fall back to `artifacts_count`; defaulting to `0`
    would report every historical run as having delivered nothing.
    """
    recorded = (run_metadata or {}).get(PUBLISHED_ARTIFACTS_COUNT_KEY)
    if isinstance(recorded, bool) or not isinstance(recorded, int):
        return artifacts_count
    return recorded


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: generate_prefixed_id("run"),
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"))
    source_version_id: Mapped[str] = mapped_column(ForeignKey("source_versions.source_version_id"))
    mode: Mapped[RunMode] = mapped_column(
        Enum(
            RunMode,
            native_enum=True,
            name="run_mode",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=RunMode.PREVIEW,
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(
            RunStatus,
            native_enum=True,
            name="run_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=RunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    artifacts_count: Mapped[int] = mapped_column(default=0)
    captured_resources_count: Mapped[int] = mapped_column(default=0)
    failure_reason: Mapped[str | None] = mapped_column(nullable=True)
    #: Caller-supplied dedupe key making run creation idempotent (#561).
    #:
    #: NULL for every ordinary run — an operator pressing "run" twice means it
    #: twice. It is set by callers that are *retried by machinery* and must not
    #: produce a second dispatch: the Temporal shard crawl writes
    #: `wizard:<wizard_run_id>:shard:<shard_key>` here, so a retried activity
    #: finds the run its earlier attempt created instead of re-scraping a
    #: government portal. The UNIQUE constraint is what enforces that — an
    #: application-level "have I already done this?" check has a race window
    #: exactly as wide as the bug it replaces.
    idempotency_key: Mapped[str | None] = mapped_column(nullable=True, unique=True)
    run_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    source = relationship("Source", back_populates="runs")
    source_version = relationship("SourceVersion", back_populates="runs")
    provider_jobs = relationship("ProviderJob", back_populates="run")

    @property
    def scope(self) -> dict:
        return dict((self.run_metadata or {}).get("scope") or {"kind": "full_source"})

    @property
    def replay(self) -> dict | None:
        replay = (self.run_metadata or {}).get("replay")
        return dict(replay) if isinstance(replay, dict) else None

    @property
    def replay_checkpoint(self) -> dict[str, Any] | None:
        checkpoint = (self.run_metadata or {}).get("replay_checkpoint")
        return dict(checkpoint) if isinstance(checkpoint, dict) else None

    @property
    def refused(self) -> bool:
        """True when this run is a refusal record, not an attempted acquisition.

        `RunService._record_refused_run` writes a terminal FAILED run when the
        ADR-0030 two-key lock blocks a dispatch, so the attempt leaves evidence
        rather than silence (#634). Reading the marker back is what makes that
        evidence auditable: without it a refusal is indistinguishable from a run
        that actually fired and failed.
        """
        return (self.run_metadata or {}).get("refused") is True

    @property
    def refusal_code(self) -> str | None:
        """The refusal's machine-readable kind, or None if it has none.

        None covers two different situations and deliberately does not distinguish
        them here: a run that was not refused at all, and a refusal recorded before
        #908 added the code. `refused` is the field that answers "was this refused";
        this one answers "what kind", and an absent value means *not classified*.
        """
        code = (self.run_metadata or {}).get("refusal_code")
        return code if isinstance(code, str) else None

    @property
    def publication_withheld(self) -> bool:
        """True when this run captured artifacts that were deliberately not published.

        `RunService._publish_pending_dispatch_events` refuses to hand a FAILED run's
        events to the broker (#853). The artifacts stay on disk and in these counts —
        they are evidence of what the source served — but nothing downstream ever
        sees them. Without this marker a withheld batch is indistinguishable from a
        broker outage, and `artifacts_count` alone would claim a delivery that did
        not happen.
        """
        return publication_withheld_from(self.run_metadata)

    @property
    def published_artifacts_count(self) -> int:
        """How many of `artifacts_count` actually reached the broker (#853).

        Captured and published are different numbers whenever a dispatch is withheld
        (FAILED run, #853) or the handoff itself fails partway (#707). Both paths
        record the real figure in `run_metadata`; every other run published what it
        captured, so the absent key falls back to `artifacts_count` rather than to a
        fabricated `0`.
        """
        return published_artifacts_count_from(self.run_metadata, self.artifacts_count)
