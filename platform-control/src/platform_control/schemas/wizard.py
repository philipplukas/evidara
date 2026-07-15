from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from platform_control.domain import ReviewTaskStatus, WizardProjectStatus, WizardRunState


class CreateWizardProjectRequest(BaseModel):
    name: str

    model_config = ConfigDict(extra="forbid")


class UpdateWizardScopeRequest(BaseModel):
    scope: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class UpdateWizardDiscoveryPlanRequest(BaseModel):
    discovery_plan: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class StartWizardPilotRunRequest(BaseModel):
    sample_limit: int | None = None

    model_config = ConfigDict(extra="forbid")


class WizardRunDecisionRequest(BaseModel):
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class WizardProjectResponse(BaseModel):
    wizard_project_id: str
    name: str
    status: WizardProjectStatus
    scope: dict[str, Any]
    discovery_plan: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WizardRunProgress(BaseModel):
    total_nodes: int = 0
    processed_nodes: int = 0
    routed_to_review: int = 0
    accepted_records: int = 0


class WizardRunQuality(BaseModel):
    confidence_distribution: dict[str, Any] = Field(default_factory=dict)
    conflict_count: int = 0
    review_backlog: int = 0


class WizardRunHealth(BaseModel):
    retry_counters: dict[str, Any] = Field(default_factory=dict)
    last_errors: list[str] = Field(default_factory=list)
    next_retry_window: str | None = None


class WizardRunStatusResponse(BaseModel):
    wizard_run_id: str
    wizard_project_id: str
    workflow_id: str | None
    state: WizardRunState
    state_entered_at: datetime
    progress: WizardRunProgress
    quality: WizardRunQuality
    health: WizardRunHealth
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateReviewTaskRequest(BaseModel):
    wizard_run_id: str
    external_id: str
    record_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ReviewDecisionRequest(BaseModel):
    """An operator's verdict on one review task.

    Replaces the batch ``POST /v1/reviews/sync-from-argilla`` poll-back: the decision
    is now pushed by whoever reviewed the task (the admin app / an operator) rather
    than pulled out of an annotation tool (ADR-0031).
    """

    decision: str
    reviewed_by: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ReviewTaskResponse(BaseModel):
    review_task_id: str
    wizard_run_id: str
    external_id: str
    record_id: str | None
    status: ReviewTaskStatus
    payload: dict[str, Any]
    decision_payload: dict[str, Any] | None
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# `CreateReviewTaskResponse` used to add `enqueue_outcome` / `enqueue_detail`, which
# reported the outcome of the outbound Argilla POST. With Argilla gone (ADR-0031)
# creation has no side channel to report, so it returns the task itself.
