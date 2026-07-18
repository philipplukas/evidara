from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.database import get_session
from platform_control.schemas.compliance_policy import (
    AttachCompliancePolicyRequest,
    CompliancePolicyListResponse,
    CompliancePolicyResponse,
    CreateCompliancePolicyRequest,
    JurisdictionPolicyAttachmentResponse,
    UpdateCompliancePolicyRequest,
)
from platform_control.schemas.errors import error_responses
from platform_control.services.compliance_policy_service import CompliancePolicyService

router = APIRouter(prefix="/v1", tags=["compliance-policies"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "/compliance-policies",
    response_model=CompliancePolicyListResponse,
)
async def list_compliance_policies(session: SessionDep) -> CompliancePolicyListResponse:
    service = CompliancePolicyService(session)
    policies = await service.list_policies()
    return CompliancePolicyListResponse(data=policies)


@router.post(
    "/compliance-policies",
    response_model=CompliancePolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_compliance_policy(
    request: CreateCompliancePolicyRequest,
    session: SessionDep,
) -> CompliancePolicyResponse:
    service = CompliancePolicyService(session)
    return await service.create_policy(request)


@router.get(
    "/compliance-policies/{compliance_policy_id}",
    response_model=CompliancePolicyResponse,
    responses=error_responses(404),
)
async def get_compliance_policy(
    compliance_policy_id: str,
    session: SessionDep,
) -> CompliancePolicyResponse:
    service = CompliancePolicyService(session)
    return await service.get_policy(compliance_policy_id)


@router.patch(
    "/compliance-policies/{compliance_policy_id}",
    response_model=CompliancePolicyResponse,
    responses=error_responses(404, 409),
)
async def update_compliance_policy(
    compliance_policy_id: str,
    request: UpdateCompliancePolicyRequest,
    session: SessionDep,
) -> CompliancePolicyResponse:
    service = CompliancePolicyService(session)
    return await service.update_policy(compliance_policy_id, request)


@router.post(
    "/jurisdictions/{jurisdiction_id}/compliance-policy",
    response_model=JurisdictionPolicyAttachmentResponse,
    responses=error_responses(404),
)
async def attach_compliance_policy(
    jurisdiction_id: str,
    request: AttachCompliancePolicyRequest,
    session: SessionDep,
) -> JurisdictionPolicyAttachmentResponse:
    service = CompliancePolicyService(session)
    jurisdiction = await service.attach_to_jurisdiction(
        jurisdiction_id=jurisdiction_id,
        compliance_policy_id=request.compliance_policy_id,
    )
    return JurisdictionPolicyAttachmentResponse(
        jurisdiction_id=jurisdiction.jurisdiction_id,
        compliance_policy_id=jurisdiction.compliance_policy_id,
    )


@router.delete(
    "/jurisdictions/{jurisdiction_id}/compliance-policy",
    response_model=JurisdictionPolicyAttachmentResponse,
    responses=error_responses(404),
)
async def detach_compliance_policy(
    jurisdiction_id: str,
    session: SessionDep,
) -> JurisdictionPolicyAttachmentResponse:
    service = CompliancePolicyService(session)
    jurisdiction = await service.detach_from_jurisdiction(jurisdiction_id)
    return JurisdictionPolicyAttachmentResponse(
        jurisdiction_id=jurisdiction.jurisdiction_id,
        compliance_policy_id=jurisdiction.compliance_policy_id,
    )
