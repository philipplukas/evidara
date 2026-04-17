from __future__ import annotations

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from platform_control.domain import RobotsMode
from platform_control.ids import generate_prefixed_id
from platform_control.models.base import Base, TimestampMixin


class CompliancePolicy(TimestampMixin, Base):
    """Per-jurisdiction compliance posture.

    Groups the knobs that govern what "polite" looks like for a scraper targeting
    this jurisdiction: robots handling, per-host rate caps, retention window,
    attribution text, contact URL surfaced in the user-agent. Attached optionally
    to a :class:`Jurisdiction` via ``Jurisdiction.compliance_policy_id``.

    Today this table is read by :class:`HostRateLimiter` (rate / concurrency)
    and the deterministic HTTP provider (contact URL). The remaining fields —
    ``robots_mode``, ``retention_days``, ``attribution_required``,
    ``attribution_text`` — are stored so the record is complete and referenced
    by downstream consumers as they come online (robots parser, retention
    enforcer, bundle attribution).
    """

    __tablename__ = "compliance_policies"

    compliance_policy_id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: generate_prefixed_id("cp")
    )
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str | None] = mapped_column(nullable=True)
    robots_mode: Mapped[RobotsMode] = mapped_column(
        Enum(
            RobotsMode,
            native_enum=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=RobotsMode.STRICT,
        server_default=RobotsMode.STRICT.value,
    )
    max_requests_per_minute_per_host: Mapped[int] = mapped_column(default=60, server_default="60")
    # Optional AIMD corridor. When min/start are set and min < max the adaptive
    # controller probes upward from `start` toward `max` on clean traffic, and
    # halves back toward `min` on 429/503/connection-error pressure. When null,
    # behaviour collapses to the static cap (equivalent to min == start == max).
    min_requests_per_minute_per_host: Mapped[int | None] = mapped_column(nullable=True)
    start_requests_per_minute_per_host: Mapped[int | None] = mapped_column(nullable=True)
    max_concurrent_per_host: Mapped[int] = mapped_column(default=2, server_default="2")
    retention_days: Mapped[int | None] = mapped_column(nullable=True)
    attribution_required: Mapped[bool] = mapped_column(default=False, server_default="0")
    attribution_text: Mapped[str | None] = mapped_column(nullable=True)
    contact_url: Mapped[str | None] = mapped_column(nullable=True)
