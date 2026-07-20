from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import get_settings
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
from platform_control.services.acquisition_provider import (
    AcquisitionReadiness,
    provider_readiness,
)
from platform_control.services.blueprint_enablement import BlueprintEnablementService
from platform_control.services.provider_registry_factory import build_provider_registry
from platform_control.services.source_blueprints import (
    list_source_blueprint_templates,
    resolve_blueprint_extractor_profile_id,
    resolve_source_blueprint,
)


def _describe_lock(
    provider: str,
    *,
    enabled: bool,
    readiness: AcquisitionReadiness,
) -> dict[str, object]:
    """Render the ADR-0030 two-key lock, with a note per closed key.

    Shared by the single-template preview and the inventory listing so the two
    can never disagree about *why* a template is inert. The notes name which key
    is shut on purpose: the config key is the one an operator owns and can flip
    themselves; the code key's remedy depends on *which* code state is shut.

    That distinction is the whole point (#743). The previous wording said the
    provider "cannot yet acquire this format" for every closed code key, which
    sent operators to an engineer to build something that already existed — the
    #628 capability question failing at the UI layer.
    """
    live_ready = readiness is AcquisitionReadiness.LIVE
    notes: list[str] = []
    if readiness is AcquisitionReadiness.SCAFFOLD:
        notes.append(
            f"Code key closed: provider '{provider}' is a scaffold — start_run is not "
            "implemented, so it cannot acquire anything yet. This needs engineering "
            "(ADR-0030)."
        )
    elif readiness is AcquisitionReadiness.AWAITING_EVIDENCE:
        notes.append(
            f"Code key closed: provider '{provider}' is implemented and verified, but no "
            "acceptance run has been captured for it yet. Dispatch a run with "
            "mode=acceptance against the live source — you do not need an engineer "
            "(ADR-0030)."
        )
    if not enabled:
        notes.append(
            "Config key closed: not enabled. Capture acceptance-run evidence, then enable "
            "this template to launch live runs (ADR-0030)."
        )
    return {
        "enabled": enabled,
        "live_ready": live_ready,
        "acquisition_readiness": readiness.value,
        "launchable": enabled and live_ready,
        "notes": notes,
    }


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

    async def describe_blueprint_lock(
        self, overlay_id: str, provider_template_id: str, provider: str
    ) -> dict[str, object]:
        """Return the two-key lock state for one template (ADR-0030, #634).

        The panel is blind to whether a template is inert unless the API tells
        it. This exposes the effective config key (DB override ?? shipped
        default), the code key (provider `live_ready`), and human-readable notes
        explaining any closed key so an inert template renders as inert *before*
        an operator invests in a source.
        """
        enablement = BlueprintEnablementService(self.session)
        enabled = await enablement.is_enabled(overlay_id, provider_template_id)
        return _describe_lock(
            provider, enabled=enabled, readiness=self._provider_readiness(provider)
        )

    def describe_blueprint_plan_notes(self, acquisition_spec: AcquisitionSpec) -> list[str]:
        """Return the provider's own `plan()` notes for a previewed spec (#634).

        Every provider already computes exactly the caveats an operator needs
        before investing in a source — seed URLs it would hit, config errors in
        the spec, and provider-specific warnings such as the gemeinde note about
        Randtitel splicing (#650). Until now `plan()` was reachable only from the
        `plan` CLI, so `blueprint-preview` returned a spec that looked correct
        while the system already knew better. This is that answer, said out loud.

        `plan()` is pure and network-free, and every provider reads only
        `source_version.acquisition_spec`, so a transient unpersisted
        `SourceVersion` carrying the previewed spec is enough to call it.
        """
        try:
            registry = build_provider_registry(get_settings())
            provider = registry.resolve_for_spec(acquisition_spec.model_dump(mode="json"))
            plan = provider.plan(
                None,
                SourceVersion(acquisition_spec=acquisition_spec.model_dump(mode="json")),
            )
            return [str(note) for note in (getattr(plan, "notes", None) or [])]
        except Exception:
            # A preview is a read-only pre-flight: it must degrade to "no notes"
            # rather than 500 because one provider's plan() raised. The lock
            # fields carry the load-bearing verdict regardless.
            return []

    def _provider_readiness(self, provider: str) -> AcquisitionReadiness:
        # Cached per service instance: build_provider_registry instantiates every
        # provider, so a template listing must not rebuild it once per row.
        cache = getattr(self, "_live_ready_cache", None)
        if cache is None:
            registry = build_provider_registry(get_settings())
            cache = registry
            self._live_ready_cache = registry
        try:
            resolved = cache.get(provider)
        except Exception:
            # An unresolvable provider is not a launchable one.
            return AcquisitionReadiness.SCAFFOLD
        return provider_readiness(resolved)

    async def list_source_blueprint_templates(self) -> list[dict[str, object]]:
        """The operator's coverage inventory: every template, with lock + provenance.

        Each row carries the two-key lock *and* where the config key's current
        value came from (`source`: an operator override, or the shipped
        `source_blueprints.yaml` default) plus that override's audit trail. The
        admin blueprint inventory (#668) needs the provenance to distinguish
        "nobody has ever touched this" from "an operator deliberately turned it
        off", which the lock booleans alone cannot express.
        """
        enablement = BlueprintEnablementService(self.session)
        enriched: list[dict[str, object]] = []
        for template in list_source_blueprint_templates():
            provider = template["provider"]
            state = await enablement.get_state(
                template["overlay_id"], template["provider_template_id"]
            )
            lock = _describe_lock(
                provider,
                enabled=state.enabled,
                readiness=self._provider_readiness(provider),
            )
            enriched.append(
                {
                    **template,
                    **lock,
                    "default_enabled": state.default_enabled,
                    "source": state.source,
                    "note": state.note,
                    "updated_by": state.updated_by,
                    "updated_at": state.updated_at,
                }
            )
        return enriched

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
            # A partial update must not reconstruct provenance from the request
            # alone: fields the client left unset still hold on the row (#619).
            overlay_id = (
                request.overlay_id
                if "overlay_id" in request.model_fields_set
                else version.overlay_id
            )
            provider_template_id = (
                request.provider_template_id
                if "provider_template_id" in request.model_fields_set
                else version.provider_template_id
            )
            acquisition_spec = self._resolve_acquisition_spec(
                acquisition_spec=request.acquisition_spec,
                overlay_id=overlay_id,
                provider_template_id=provider_template_id,
            )
            spec_payload = acquisition_spec.model_dump(mode="json")
            version.acquisition_spec = spec_payload
            provenance = self._blueprint_provenance_for_spec(
                spec_payload=spec_payload,
                overlay_id=overlay_id,
                provider_template_id=provider_template_id,
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
    def _blueprint_provenance_for_spec(
        *,
        spec_payload: dict[str, object],
        overlay_id: str | None,
        provider_template_id: str | None,
    ) -> dict[str, str | None]:
        """Provenance for an *edited* version, judged by the spec itself (#619).

        `_blueprint_provenance` keys off "was an explicit spec supplied?", which
        is the right question at creation time but the wrong one on update: the
        admin editor cannot express "I did not touch the spec" and sends a full
        one on every save, so an unrelated label edit looked like a hand-written
        replacement and silently dropped the template id.

        Here the rule is stated directly instead: provenance survives exactly
        while the persisted spec still *is* the blueprint's output. Editing the
        spec away from the template still clears it, so the run-launch path can
        never gate a hand-written spec on a template it no longer follows.
        """
        if not (overlay_id and provider_template_id):
            return {"overlay_id": None, "provider_template_id": None}
        try:
            blueprint = resolve_source_blueprint(
                overlay_id=overlay_id,
                provider_template_id=provider_template_id,
            )
            expected = parse_acquisition_spec(blueprint).model_dump(mode="json")
        except Exception:
            return {"overlay_id": None, "provider_template_id": None}
        if expected != spec_payload:
            return {"overlay_id": None, "provider_template_id": None}
        return {"overlay_id": overlay_id, "provider_template_id": provider_template_id}

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
