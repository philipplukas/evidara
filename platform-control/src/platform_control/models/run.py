from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_control.domain import RunMode, RunStatus
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin, utcnow


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
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=RunMode.PREVIEW,
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(
            RunStatus,
            native_enum=False,
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
