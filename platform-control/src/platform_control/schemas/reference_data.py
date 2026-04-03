from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JurisdictionResponse(BaseModel):
    jurisdiction_id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JurisdictionListResponse(BaseModel):
    data: list[JurisdictionResponse]


class CreateJurisdictionRequest(BaseModel):
    name: str
    slug: str


class UpdateJurisdictionRequest(BaseModel):
    name: str | None = None
    slug: str | None = None


class AuthorityResponse(BaseModel):
    authority_id: str
    jurisdiction_id: str | None
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthorityListResponse(BaseModel):
    data: list[AuthorityResponse]


class CreateAuthorityRequest(BaseModel):
    jurisdiction_id: str | None = None
    name: str
    slug: str


class UpdateAuthorityRequest(BaseModel):
    jurisdiction_id: str | None = None
    name: str | None = None
    slug: str | None = None
