from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class JurisdictionResponse(BaseModel):
    jurisdiction_id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JurisdictionListResponse(BaseModel):
    """One page of jurisdictions plus the total hit count.

    ``total``/``limit``/``offset`` were added in #616. Before that this response
    was ``data`` only, so the admin concluded the array was unbounded, paged it
    client-side and reported the page length as the count — over 2,169 seeded
    jurisdictions.
    """

    data: list[JurisdictionResponse]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class CreateJurisdictionRequest(BaseModel):
    name: str
    slug: str


class UpdateJurisdictionRequest(BaseModel):
    name: str | None = None
    slug: str | None = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> UpdateJurisdictionRequest:
        if self.name is None and self.slug is None:
            raise ValueError("At least one field must be provided.")
        return self


class AuthorityResponse(BaseModel):
    authority_id: str
    jurisdiction_id: str | None
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthorityListResponse(BaseModel):
    """One page of authorities plus the total hit count. See #616."""

    data: list[AuthorityResponse]
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class CreateAuthorityRequest(BaseModel):
    jurisdiction_id: str | None = None
    name: str
    slug: str


class UpdateAuthorityRequest(BaseModel):
    jurisdiction_id: str | None = None
    name: str | None = None
    slug: str | None = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> UpdateAuthorityRequest:
        if self.jurisdiction_id is None and self.name is None and self.slug is None:
            raise ValueError("At least one field must be provided.")
        return self


class HierarchySyncCountsResponse(BaseModel):
    created: int
    updated: int
    unchanged: int


class HierarchySyncResponse(BaseModel):
    """Response from ``POST /v1/reference-data/hierarchy/sync``.

    The endpoint is a thin shim over ``ReferenceDataSeeder`` (issue #312).
    """

    dry_run: bool
    jurisdictions: HierarchySyncCountsResponse
    authorities: HierarchySyncCountsResponse
