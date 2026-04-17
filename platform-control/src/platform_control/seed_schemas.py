from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from platform_control.domain import RobotsMode


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
    """

    compliance_policy_id: str
    name: str
    description: str | None = None
    robots_mode: RobotsMode = RobotsMode.STRICT
    max_requests_per_minute_per_host: int = Field(default=60, ge=1, le=10_000)
    max_concurrent_per_host: int = Field(default=2, ge=1, le=100)
    retention_days: int | None = Field(default=None, ge=1, le=36_500)
    attribution_required: bool = False
    attribution_text: str | None = None
    contact_url: str | None = None

    model_config = ConfigDict(extra="forbid")


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
