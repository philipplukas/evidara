from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from platform_control.domain import RobotsMode


def _validate_rate_corridor(
    *,
    min_rpm: int | None,
    start_rpm: int | None,
    max_rpm: int,
) -> None:
    """Enforce min <= start <= max when either of the optional fields is set.

    Shared between seed + API schemas so the CRUD API and the YAML seeder reject
    inconsistent corridors with the same message. Either both min and start must
    be set, or neither — a half-declared corridor is ambiguous and rejected.
    """
    if min_rpm is None and start_rpm is None:
        return
    if min_rpm is None or start_rpm is None:
        raise ValueError(
            "min_requests_per_minute_per_host and start_requests_per_minute_per_host "
            "must be set together or both omitted."
        )
    if min_rpm > max_rpm:
        raise ValueError(
            "min_requests_per_minute_per_host must be <= max_requests_per_minute_per_host."
        )
    if start_rpm < min_rpm or start_rpm > max_rpm:
        raise ValueError("start_requests_per_minute_per_host must fall within [min, max].")


class SeedBundle[TItem: BaseModel](BaseModel):
    version: int
    items: list[TItem]

    model_config = ConfigDict(extra="forbid")


class CompliancePolicySeed(BaseModel):
    """Declarative compliance posture for a jurisdiction.

    Defaults mirror ``CompliancePolicy`` model defaults so a minimal seed entry
    (``compliance_policy_id`` + ``name``) declares the safest possible policy.
    Operators raise caps or flip ``robots_mode`` explicitly when a source's
    licence justifies it.

    ``min_requests_per_minute_per_host`` + ``start_requests_per_minute_per_host``
    enable the AIMD adaptive layer. When unset, the policy uses a static cap
    equal to ``max_requests_per_minute_per_host``.
    """

    compliance_policy_id: str
    name: str
    description: str | None = None
    robots_mode: RobotsMode = RobotsMode.STRICT
    max_requests_per_minute_per_host: int = Field(default=60, ge=1, le=10_000)
    min_requests_per_minute_per_host: int | None = Field(default=None, ge=1, le=10_000)
    start_requests_per_minute_per_host: int | None = Field(default=None, ge=1, le=10_000)
    max_concurrent_per_host: int = Field(default=2, ge=1, le=100)
    retention_days: int | None = Field(default=None, ge=1, le=36_500)
    attribution_required: bool = False
    attribution_text: str | None = None
    contact_url: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_corridor(self) -> CompliancePolicySeed:
        _validate_rate_corridor(
            min_rpm=self.min_requests_per_minute_per_host,
            start_rpm=self.start_requests_per_minute_per_host,
            max_rpm=self.max_requests_per_minute_per_host,
        )
        return self


class JurisdictionSeed(BaseModel):
    jurisdiction_id: str
    slug: str
    name: str
    compliance_policy_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class AuthoritySeed(BaseModel):
    authority_id: str
    jurisdiction_id: str
    slug: str
    name: str

    model_config = ConfigDict(extra="forbid")


class ExtractorProfileSeed(BaseModel):
    extractor_profile_id: str
    name: str
    source_family: str
    version: str
    definition: dict

    model_config = ConfigDict(extra="forbid")


class SeedSummary(BaseModel):
    dry_run: bool
    seed_dir: Path
    created: dict[str, int]
    updated: dict[str, int]
    unchanged: dict[str, int]

    model_config = ConfigDict(arbitrary_types_allowed=True)
