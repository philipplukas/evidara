from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class SeedBundle[TItem: BaseModel](BaseModel):
    version: int
    items: list[TItem]

    model_config = ConfigDict(extra="forbid")


class JurisdictionSeed(BaseModel):
    jurisdiction_id: str
    slug: str
    name: str

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
