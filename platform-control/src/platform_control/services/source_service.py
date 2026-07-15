from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.domain import SourceVersionStatus
from platform_control.errors import InvalidStateTransitionError, NotFoundError
from platform_control.models.authority import Authority, Jurisdiction
from platform_control.models.extractor_profile import ExtractorProfile
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.schemas.source import (
    AcquisitionSpec,
    CreateSourceRequest,
    CreateSourceVersionRequest,
    CreateSourceWithVersionRequest,
    SourceBlueprintPreviewRequest,
    UpdateSourceVersionRequest,
    parse_acquisition_spec,
)
from platform_control.services.source_blueprints import (
    list_source_blueprint_templates,
    resolve_blueprint_extractor_profile_id,
    resolve_source_blueprint,
)


class SourceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_sources(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        q: str | None = None,
    ) -> tuple[list[Source], int]:
        base = select(Source).order_by(Source.created_at.desc())
        if q:
            base = base.where(Source.name.ilike(f"%{q}%"))
        count_result = await self.session.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar() or 0
        result = await self.session.scalars(base.limit(limit).offset(offset))
        return list(result), total

    async def get_source(self, source_id: str) -> Source:
        source = await self.session.get(Source, source_id)
        if source is None:
            raise NotFoundError(f"Source not found: {source_id}")
        return source

    async def create_source(self, request: CreateSourceRequest) -> Source:
        await self._validate_source_reference_data(
            jurisdiction_id=request.jurisdiction_id,
            authority_id=request.authority_id,
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

    async def create_source_with_initial_version(
        self,
        request: CreateSourceWithVersionRequest,
    ) -> tuple[Source, SourceVersion]:
        await self._validate_source_reference_data(
            jurisdiction_id=request.source.jurisdiction_id,
            authority_id=request.source.authority_id,
        )
        extractor_profile_id = await self._resolve_extractor_profile_id(
            requested=request.source_version.extractor_profile_id,
            acquisition_spec=request.source_version.acquisition_spec,
            overlay_id=request.source_version.overlay_id,
            provider_template_id=request.source_version.provider_template_id,
        )
        acquisition_spec = self._resolve_acquisition_spec(
            acquisition_spec=request.source_version.acquisition_spec,
            overlay_id=request.source_version.overlay_id,
            provider_template_id=request.source_version.provider_template_id,
        )

        source = Source(
            name=request.source.name,
            description=request.source.description,
            jurisdiction_id=request.source.jurisdiction_id,
            authority_id=request.source.authority_id,
            source_type=request.source.source_type,
            document_family=request.source.document_family,
        )
        self.session.add(source)
        await self.session.flush()

        source_version = SourceVersion(
            source_id=source.source_id,
            extractor_profile_id=extractor_profile_id,
            version_label=request.source_version.version_label,
            execution_mode=request.source_version.execution_mode,
            acquisition_spec=acquisition_spec.model_dump(mode="json"),
            **self._blueprint_provenance(
                acquisition_spec=request.source_version.acquisition_spec,
                overlay_id=request.source_version.overlay_id,
                provider_template_id=request.source_version.provider_template_id,
            ),
        )
        self.session.add(source_version)
        await self.session.commit()
        await self.session.refresh(source)
        await self.session.refresh(source_version)
        return source, source_version

    async def preview_source_blueprint(
        self,
        request: SourceBlueprintPreviewRequest,
    ) -> AcquisitionSpec:
        return self._resolve_acquisition_spec(
            acquisition_spec=None,
            overlay_id=request.overlay_id,
            provider_template_id=request.provider_template_id,
        )

    async def list_source_blueprint_templates(self) -> list[dict[str, str]]:
        return list_source_blueprint_templates()

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
        extractor_profile_id = await self._resolve_extractor_profile_id(
            requested=request.extractor_profile_id,
            acquisition_spec=request.acquisition_spec,
            overlay_id=request.overlay_id,
            provider_template_id=request.provider_template_id,
        )

        acquisition_spec = self._resolve_acquisition_spec(
            acquisition_spec=request.acquisition_spec,
            overlay_id=request.overlay_id,
            provider_template_id=request.provider_template_id,
        )

        version = SourceVersion(
            source_id=source_id,
            extractor_profile_id=extractor_profile_id,
            version_label=request.version_label,
            execution_mode=request.execution_mode,
            acquisition_spec=acquisition_spec.model_dump(mode="json"),
            **self._blueprint_provenance(
                acquisition_spec=request.acquisition_spec,
                overlay_id=request.overlay_id,
                provider_template_id=request.provider_template_id,
            ),
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
        if (
            "acquisition_spec" in request.model_fields_set
            or "overlay_id" in request.model_fields_set
            or "provider_template_id" in request.model_fields_set
        ):
            acquisition_spec = self._resolve_acquisition_spec(
                acquisition_spec=request.acquisition_spec,
                overlay_id=request.overlay_id,
                provider_template_id=request.provider_template_id,
            )
            version.acquisition_spec = acquisition_spec.model_dump(mode="json")
            # Provenance follows the spec: re-pointing a version at a blueprint
            # records the template; replacing it with a hand-written spec clears it.
            provenance = self._blueprint_provenance(
                acquisition_spec=request.acquisition_spec,
                overlay_id=request.overlay_id,
                provider_template_id=request.provider_template_id,
            )
            version.overlay_id = provenance["overlay_id"]
            version.provider_template_id = provenance["provider_template_id"]
        if "extractor_profile_id" in payload:
            version.extractor_profile_id = payload["extractor_profile_id"]
        if request.execution_mode is not None:
            version.execution_mode = request.execution_mode

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

    async def _validate_source_reference_data(
        self,
        *,
        jurisdiction_id: str,
        authority_id: str,
    ) -> None:
        jurisdiction = await self.session.get(Jurisdiction, jurisdiction_id)
        if jurisdiction is None:
            raise NotFoundError(f"Jurisdiction not found: {jurisdiction_id}")

        authority = await self.session.get(Authority, authority_id)
        if authority is None:
            raise NotFoundError(f"Authority not found: {authority_id}")
        if authority.jurisdiction_id and authority.jurisdiction_id != jurisdiction.jurisdiction_id:
            raise InvalidStateTransitionError(
                "Authority does not belong to the requested jurisdiction."
            )

    async def _resolve_extractor_profile_id(
        self,
        *,
        requested: str | None,
        acquisition_spec: AcquisitionSpec | None,
        overlay_id: str | None,
        provider_template_id: str | None,
    ) -> str | None:
        """Resolve the effective extractor_profile_id and validate it exists.

        An explicit request value wins and is validated strictly. Otherwise,
        when the version is created from a blueprint (no explicit
        acquisition_spec), fall back to the template's default
        extractor_profile_id — e.g. Fedlex legislation templates default to
        exp_legislation_v1 (#532). The blueprint default is best-effort
        enrichment: if that profile is not present it is skipped rather than
        blocking source creation (blueprint profile ids are integrity-checked
        against the seed by test_blueprint_provider_parity).
        """
        if requested is not None:
            if await self.session.get(ExtractorProfile, requested) is None:
                raise NotFoundError(f"Extractor profile not found: {requested}")
            return requested
        if acquisition_spec is None and overlay_id and provider_template_id:
            default_id = resolve_blueprint_extractor_profile_id(overlay_id, provider_template_id)
            if default_id is not None and await self.session.get(ExtractorProfile, default_id):
                return default_id
        return None

    @staticmethod
    def _blueprint_provenance(
        *,
        acquisition_spec: AcquisitionSpec | None,
        overlay_id: str | None,
        provider_template_id: str | None,
    ) -> dict[str, str | None]:
        """Blueprint provenance to persist on the SourceVersion (ADR-0030).

        Only set when the version is created from a blueprint template; an
        explicit acquisition_spec wins over blueprint fields in
        _resolve_acquisition_spec, so it must clear the provenance too — else
        the run-launch path would gate a hand-written spec on a template the
        version no longer uses.
        """
        if acquisition_spec is None and overlay_id and provider_template_id:
            return {"overlay_id": overlay_id, "provider_template_id": provider_template_id}
        return {"overlay_id": None, "provider_template_id": None}

    @staticmethod
    def _resolve_acquisition_spec(
        *,
        acquisition_spec: AcquisitionSpec | None,
        overlay_id: str | None,
        provider_template_id: str | None,
    ) -> AcquisitionSpec:
        if acquisition_spec is not None:
            return acquisition_spec
        if overlay_id and provider_template_id:
            blueprint = resolve_source_blueprint(
                overlay_id=overlay_id,
                provider_template_id=provider_template_id,
            )
            return parse_acquisition_spec(blueprint)
        raise InvalidStateTransitionError(
            "Provide acquisition_spec or overlay_id/provider_template_id."
        )
