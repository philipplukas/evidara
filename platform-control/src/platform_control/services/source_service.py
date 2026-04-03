from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import SourceVersionStatus
from platform_control.errors import InvalidStateTransitionError, NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.extractor_profile import ExtractorProfile
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.source import (
    CreateSourceRequest,
    CreateSourceVersionRequest,
    UpdateSourceVersionRequest,
)


class SourceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_sources(self) -> list[Source]:
        result = await self.session.scalars(select(Source).order_by(Source.created_at.desc()))
        return list(result)

    async def get_source(self, source_id: str) -> Source:
        source = await self.session.get(Source, source_id)
        if source is None:
            raise NotFoundError(f"Source not found: {source_id}")
        return source

    async def create_source(self, request: CreateSourceRequest) -> Source:
        jurisdiction = await self.session.get(Jurisdiction, request.jurisdiction_id)
        if jurisdiction is None:
            raise NotFoundError(f"Jurisdiction not found: {request.jurisdiction_id}")

        authority = await self.session.get(Authority, request.authority_id)
        if authority is None:
            raise NotFoundError(f"Authority not found: {request.authority_id}")
        if authority.jurisdiction_id and authority.jurisdiction_id != jurisdiction.jurisdiction_id:
            raise InvalidStateTransitionError(
                "Authority does not belong to the requested jurisdiction."
            )

        source = Source(
            name=request.name,
            description=request.description,
            jurisdiction_id=request.jurisdiction_id,
            authority_id=request.authority_id,
            source_type=request.source_type,
            document_family=request.document_family,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def list_source_versions(self, source_id: str) -> list[SourceVersion]:
        await self.get_source(source_id)
        result = await self.session.scalars(
            select(SourceVersion)
            .where(SourceVersion.source_id == source_id)
            .order_by(SourceVersion.created_at.desc())
        )
        return list(result)

    async def create_source_version(
        self,
        source_id: str,
        request: CreateSourceVersionRequest,
    ) -> SourceVersion:
        await self.get_source(source_id)
        if request.extractor_profile_id:
            extractor_profile = await self.session.get(
                ExtractorProfile, request.extractor_profile_id
            )
            if extractor_profile is None:
                raise NotFoundError(f"Extractor profile not found: {request.extractor_profile_id}")

        version = SourceVersion(
            source_id=source_id,
            extractor_profile_id=request.extractor_profile_id,
            version_label=request.version_label,
            acquisition_spec=request.acquisition_spec.model_dump(mode="json"),
        )
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(version)
        return version

    async def update_source_version(
        self,
        source_version_id: str,
        request: UpdateSourceVersionRequest,
    ) -> SourceVersion:
        version = await self._get_source_version(source_version_id)
        if version.status not in {SourceVersionStatus.DRAFT, SourceVersionStatus.REJECTED}:
            raise InvalidStateTransitionError(
                f"Cannot edit source version in status {version.status}."
            )

        payload = request.model_dump(exclude_unset=True)
        if "extractor_profile_id" in payload and payload["extractor_profile_id"] is not None:
            extractor_profile = await self.session.get(
                ExtractorProfile,
                payload["extractor_profile_id"],
            )
            if extractor_profile is None:
                raise NotFoundError(
                    f"Extractor profile not found: {payload['extractor_profile_id']}"
                )

        if "version_label" in payload:
            version.version_label = payload["version_label"]
        if "acquisition_spec" in request.model_fields_set and request.acquisition_spec is not None:
            version.acquisition_spec = request.acquisition_spec.model_dump(mode="json")
        if "extractor_profile_id" in payload:
            version.extractor_profile_id = payload["extractor_profile_id"]

        await self.session.commit()
        await self.session.refresh(version)
        return version

    async def approve_source_version(self, source_version_id: str) -> SourceVersion:
        version = await self._get_source_version(source_version_id)
        if version.status not in {
            SourceVersionStatus.DRAFT,
            SourceVersionStatus.PENDING_APPROVAL,
        }:
            raise InvalidStateTransitionError(
                f"Cannot approve source version in status {version.status}."
            )
        version.status = SourceVersionStatus.APPROVED
        await self.session.commit()
        await self.session.refresh(version)
        return version

    async def reject_source_version(self, source_version_id: str) -> SourceVersion:
        version = await self._get_source_version(source_version_id)
        if version.status not in {
            SourceVersionStatus.DRAFT,
            SourceVersionStatus.PENDING_APPROVAL,
        }:
            raise InvalidStateTransitionError(
                f"Cannot reject source version in status {version.status}."
            )
        version.status = SourceVersionStatus.REJECTED
        await self.session.commit()
        await self.session.refresh(version)
        return version

    async def _get_source_version(self, source_version_id: str) -> SourceVersion:
        version = await self.session.get(SourceVersion, source_version_id)
        if version is None:
            raise NotFoundError(f"Source version not found: {source_version_id}")
        return version
