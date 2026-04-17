from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from platform_control.domain import RobotsMode
from platform_control.seed_schemas import _validate_rate_corridor


class CreateCompliancePolicyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    robots_mode: RobotsMode = RobotsMode.STRICT
    max_requests_per_minute_per_host: int = Field(default=60, ge=1, le=10_000)
    min_requests_per_minute_per_host: int | None = Field(default=None, ge=1, le=10_000)
    start_requests_per_minute_per_host: int | None = Field(default=None, ge=1, le=10_000)
    max_concurrent_per_host: int = Field(default=2, ge=1, le=100)
    retention_days: int | None = Field(default=None, ge=1, le=36_500)
    attribution_required: bool = False
    attribution_text: str | None = None
    contact_url: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_corridor(self) -> CreateCompliancePolicyRequest:
        _validate_rate_corridor(
            min_rpm=self.min_requests_per_minute_per_host,
            start_rpm=self.start_requests_per_minute_per_host,
            max_rpm=self.max_requests_per_minute_per_host,
        )
        return self


class UpdateCompliancePolicyRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    robots_mode: RobotsMode | None = None
    max_requests_per_minute_per_host: int | None = Field(default=None, ge=1, le=10_000)
    min_requests_per_minute_per_host: int | None = Field(default=None, ge=1, le=10_000)
    start_requests_per_minute_per_host: int | None = Field(default=None, ge=1, le=10_000)
    max_concurrent_per_host: int | None = Field(default=None, ge=1, le=100)
    retention_days: int | None = Field(default=None, ge=1, le=36_500)
    attribution_required: bool | None = None
    attribution_text: str | None = None
    contact_url: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_has_changes(self) -> UpdateCompliancePolicyRequest:
        if all(
            value is None
            for value in (
                self.name,
                self.description,
                self.robots_mode,
                self.max_requests_per_minute_per_host,
                self.min_requests_per_minute_per_host,
                self.start_requests_per_minute_per_host,
                self.max_concurrent_per_host,
                self.retention_days,
                self.attribution_required,
                self.attribution_text,
                self.contact_url,
            )
        ):
            raise ValueError("At least one field must be provided.")
        # Corridor validation on patches only fires when all three fields are
        # settled — if the operator patches one without the others we defer
        # validation to the service layer, which has the persisted values.
        return self


class CompliancePolicyResponse(BaseModel):
    compliance_policy_id: str
    name: str
    description: str | None
    robots_mode: RobotsMode
    max_requests_per_minute_per_host: int
    min_requests_per_minute_per_host: int | None
    start_requests_per_minute_per_host: int | None
    max_concurrent_per_host: int
    retention_days: int | None
    attribution_required: bool
    attribution_text: str | None
    contact_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompliancePolicyListResponse(BaseModel):
    data: list[CompliancePolicyResponse]


class AttachCompliancePolicyRequest(BaseModel):
    compliance_policy_id: str


class JurisdictionPolicyAttachmentResponse(BaseModel):
    jurisdiction_id: str
    compliance_policy_id: str | None
