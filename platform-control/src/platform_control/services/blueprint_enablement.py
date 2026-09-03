"""Operator-reachable resolution of the ADR-0030 config-owner key (#632).

The two-key lock has a config-owner key (`enabled`) and a code-owner key
(`live_ready`). The code key is an engineering assertion and rightly lives in
code. The config key is *operational state* — the thing an operator flips after
capturing acceptance-run evidence — yet it used to live in `source_blueprints.yaml`
inside the Python package, so flipping it meant a PR and a deploy. That made every
new source an engineering project and broke the #628 thesis.

This service resolves the effective config key as **DB override ?? shipped
default**: `blueprint_template_overrides` holds operator flips (with an audit
trail), and `source_blueprints.yaml` remains the fail-closed shipped default when
no override exists. `set_enabled` is the flip an operator reaches through the API.

`set_enabled` is the *write*, not the *guard*. Every operator-facing flip goes through
`BlueprintEnablementGuard.flip` below, which derives the ADR-0030 refusals server-side
and proves the write by read-back, so the CLI and the admin panel cannot diverge on how
hard the platform's most dangerous action is to take (#854, #846). The refusal
vocabulary lives in `blueprint_enablement_guard.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.config import get_settings
from platform_control.errors import BlueprintTemplateNotEnabledError, NotFoundError
from platform_control.models.blueprint_template_override import BlueprintTemplateOverride
from platform_control.models.run import Run
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    AcquisitionReadiness,
    provider_readiness,
)
from platform_control.services.blueprint_enablement_guard import (
    AcceptanceVerdict,
    EvidenceBinding,
    Refusal,
    acceptance_evidence_verdict,
    evidence_binding,
    flip_verdict,
    read_back_problems,
)
from platform_control.services.provider_registry_factory import build_provider_registry
from platform_control.services.source_blueprints import (
    is_source_blueprint_default_enabled,
    resolve_source_blueprint,
)


def _enum_value(value: object) -> str:
    """Render a `StrEnum` column as its wire value, tolerating a plain string."""
    return str(getattr(value, "value", value))


@dataclass(frozen=True)
class BlueprintEnablementState:
    """The effective config-owner key for one template, and its provenance."""

    overlay_id: str
    provider_template_id: str
    enabled: bool
    default_enabled: bool
    source: str  # "override" (an operator flipped it) | "default" (shipped YAML)
    note: str | None
    updated_by: str | None
    updated_at: datetime | None


class BlueprintEnablementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_override(
        self, overlay_id: str, provider_template_id: str
    ) -> BlueprintTemplateOverride | None:
        return await self.session.scalar(
            select(BlueprintTemplateOverride).where(
                BlueprintTemplateOverride.overlay_id == overlay_id,
                BlueprintTemplateOverride.provider_template_id == provider_template_id,
            )
        )

    async def is_enabled(self, overlay_id: str, provider_template_id: str) -> bool:
        """Effective config key: DB override wins, else the shipped default.

        Raises NotFoundError if the template does not exist in the shipped
        blueprints (so unknown templates fail closed, not silently true).
        """
        override = await self._get_override(overlay_id, provider_template_id)
        if override is not None:
            return override.enabled
        return is_source_blueprint_default_enabled(overlay_id, provider_template_id)

    async def get_state(
        self, overlay_id: str, provider_template_id: str
    ) -> BlueprintEnablementState:
        default_enabled = is_source_blueprint_default_enabled(overlay_id, provider_template_id)
        override = await self._get_override(overlay_id, provider_template_id)
        if override is not None:
            return BlueprintEnablementState(
                overlay_id=overlay_id,
                provider_template_id=provider_template_id,
                enabled=override.enabled,
                default_enabled=default_enabled,
                source="override",
                note=override.note,
                updated_by=override.updated_by,
                updated_at=override.updated_at,
            )
        return BlueprintEnablementState(
            overlay_id=overlay_id,
            provider_template_id=provider_template_id,
            enabled=default_enabled,
            default_enabled=default_enabled,
            source="default",
            note=None,
            updated_by=None,
            updated_at=None,
        )

    async def require_enabled(self, overlay_id: str, provider_template_id: str) -> None:
        """Raise BlueprintTemplateNotEnabledError unless the effective key is on.

        Config-owner half of the run-launch two-key lock. A template that has
        been removed from the shipped blueprints since a source version was
        created is treated as not enabled (fail closed) rather than as a 404.
        """
        try:
            enabled = await self.is_enabled(overlay_id, provider_template_id)
        except NotFoundError as exc:
            raise BlueprintTemplateNotEnabledError(
                f"Blueprint template '{overlay_id}/{provider_template_id}' no longer exists, "
                "so it cannot be launched for live acquisition."
            ) from exc
        if not enabled:
            # The remedy differs by how the key came to be shut, so the message
            # must too (#768). Telling an operator who deliberately closed the key
            # to "capture acceptance-run evidence" misreads their own kill switch
            # as a key that was never earned.
            state = await self.get_state(overlay_id, provider_template_id)
            if state.source == "override":
                raise BlueprintTemplateNotEnabledError(
                    f"Blueprint template '{overlay_id}/{provider_template_id}' was turned off "
                    "by an operator. Turn the config key back on from the admin panel's "
                    "Blueprints inventory to run against this portal again (ADR-0030)."
                )
            raise BlueprintTemplateNotEnabledError(
                f"Blueprint template '{overlay_id}/{provider_template_id}' is not enabled for "
                "live acquisition. Capture acceptance-run evidence with `mode=acceptance`, then "
                "turn the config key on from the admin panel's Blueprints inventory "
                "(ADR-0030, #632, #668)."
            )

    async def set_enabled(
        self,
        overlay_id: str,
        provider_template_id: str,
        *,
        enabled: bool,
        note: str | None = None,
        actor: str | None = None,
    ) -> BlueprintEnablementState:
        """Flip the operator-reachable config key and record who/when/why.

        Raises NotFoundError if the template is not a known shipped blueprint —
        an operator cannot enable a template that does not exist.
        """
        # Existence check: raises NotFoundError for an unknown template.
        is_source_blueprint_default_enabled(overlay_id, provider_template_id)

        override = await self._get_override(overlay_id, provider_template_id)
        if override is None:
            override = BlueprintTemplateOverride(
                overlay_id=overlay_id,
                provider_template_id=provider_template_id,
                enabled=enabled,
                note=note,
                updated_by=actor,
            )
            self.session.add(override)
        else:
            override.enabled = enabled
            override.note = note
            override.updated_by = actor
        await self.session.flush()
        return await self.get_state(overlay_id, provider_template_id)


@dataclass(frozen=True)
class GuardedFlipOutcome:
    """What the ADR-0030 config-key guard decided, and what it did about it (#854).

    A refusal carries ``write_attempted = False``: nothing was written, so an operator
    can act on the codes and retry. ``applied = False`` with ``write_attempted = True``
    is the other bad case — the override row was written but re-reading it does not
    confirm the flip, which must never be reported as success (#631, #713).
    """

    overlay_id: str
    provider_template_id: str
    provider: str | None
    readiness: str
    state_before: BlueprintEnablementState
    state: BlueprintEnablementState | None
    refusals: list[Refusal] = field(default_factory=list)
    needs_human: bool = False
    needs_human_reasons: list[str] = field(default_factory=list)
    evidence_run_id: str | None = None
    evidence_binding: str | None = None
    acceptance_verdict: AcceptanceVerdict | None = None
    applied: bool = False
    write_attempted: bool = False

    @property
    def refused(self) -> bool:
        return bool(self.refusals)


class BlueprintEnablementGuard:
    """Derive and enforce the ADR-0030 config-key refusals, then prove the write.

    This is the single guard both clients go through (#854). It used to exist twice —
    once in ``evidara_cli.coverage`` with eight named refusals, and once in the admin
    dialog as "the note must not be empty" — so the easier path was the weaker one and
    the CLI's guard was advisory rather than enforced.

    Kept next to :class:`BlueprintEnablementService` rather than inside it because the
    service's other caller is the run-launch two-key lock, which reads the key on every
    dispatch and must not pay for a provider registry to do it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.enablement = BlueprintEnablementService(session)
        self._registry = None

    def _readiness(self, provider: str | None) -> AcquisitionReadiness:
        if self._registry is None:
            self._registry = build_provider_registry(get_settings())
        try:
            resolved = self._registry.get(str(provider))
        except Exception:
            # An unresolvable provider is not a live one.
            return AcquisitionReadiness.SCAFFOLD
        return provider_readiness(resolved)

    async def _evidence_context(
        self,
        evidence_run_id: str,
        *,
        overlay_id: str,
        provider_template_id: str,
        template_provider: str | None,
        template_spec: dict,
    ) -> tuple[bool, AcceptanceVerdict | None, EvidenceBinding | None]:
        """Resolve the cited run, its version, and what the two of them prove.

        The version carries both halves: ``execution_mode`` (a SHADOW version replays
        fixtures and evidences nothing about the portal, ADR-0030 §2) and the blueprint
        provenance that binds the run to *this* template rather than merely to its
        provider (#846).
        """
        run = await self.session.get(Run, evidence_run_id)
        if run is None:
            return False, None, None

        version = await self.session.get(SourceVersion, run.source_version_id)
        verdict = acceptance_evidence_verdict(
            run_id=run.run_id,
            refused=run.refused,
            status=_enum_value(run.status),
            mode=_enum_value(run.mode),
            execution_mode=None if version is None else _enum_value(version.execution_mode),
            captured_resources_count=run.captured_resources_count,
        )
        binding = evidence_binding(
            template_overlay_id=overlay_id,
            template_provider_template_id=provider_template_id,
            template_provider=template_provider,
            template_spec=template_spec,
            version_overlay_id=None if version is None else version.overlay_id,
            version_provider_template_id=(
                None if version is None else version.provider_template_id
            ),
            version_spec=None if version is None else version.acquisition_spec,
        )
        return True, verdict, binding

    async def flip(
        self,
        overlay_id: str,
        provider_template_id: str,
        *,
        enabled: bool,
        note: str | None,
        evidence_run_id: str | None = None,
        reopen_operator_kill_switch: bool = False,
        acknowledge_provider_below_live: bool = False,
        actor: str | None = None,
    ) -> GuardedFlipOutcome:
        """Flip the config key only if the evidence earns it, and prove it landed.

        Raises ``NotFoundError`` for a template that is not a shipped blueprint — an
        operator cannot enable something that does not exist, and that is a bad
        reference rather than a policy refusal.
        """
        # Raises NotFoundError for an unknown template.
        template_spec = resolve_source_blueprint(overlay_id, provider_template_id)
        raw_provider = template_spec.get("provider")
        template_provider = str(raw_provider) if raw_provider is not None else None
        readiness = self._readiness(template_provider)
        state_before = await self.enablement.get_state(overlay_id, provider_template_id)

        run_exists = False
        verdict: AcceptanceVerdict | None = None
        binding: EvidenceBinding | None = None
        if enabled and evidence_run_id:
            run_exists, verdict, binding = await self._evidence_context(
                evidence_run_id,
                overlay_id=overlay_id,
                provider_template_id=provider_template_id,
                template_provider=template_provider,
                template_spec=template_spec,
            )

        decision = flip_verdict(
            desired_enabled=enabled,
            note=note,
            readiness=readiness.value,
            config_key_provenance=state_before.source,
            evidence_run_id=evidence_run_id,
            evidence_run_exists=run_exists,
            acceptance=verdict,
            binding=binding,
            reopen_operator_kill_switch=reopen_operator_kill_switch,
            acknowledge_provider_below_live=acknowledge_provider_below_live,
        )

        base = {
            "overlay_id": overlay_id,
            "provider_template_id": provider_template_id,
            "provider": template_provider,
            "readiness": readiness.value,
            "state_before": state_before,
            "evidence_run_id": evidence_run_id,
            "evidence_binding": None if binding is None else binding.strength,
            "acceptance_verdict": verdict,
        }

        if decision.refused:
            return GuardedFlipOutcome(
                state=None,
                refusals=decision.refusals,
                needs_human=True,
                needs_human_reasons=decision.needs_human_reasons,
                applied=False,
                write_attempted=False,
                **base,
            )

        await self.enablement.set_enabled(
            overlay_id,
            provider_template_id,
            enabled=enabled,
            note=note,
            actor=actor,
        )
        await self.session.commit()

        # The write returning is not the proof. Re-read the state — the commit above
        # expired the identity map, so this is a fresh SELECT — and require both the
        # effective key and an `override` provenance. Either alone is also satisfied by
        # a write that silently did nothing (#631, #713).
        state_after = await self.enablement.get_state(overlay_id, provider_template_id)
        problems = read_back_problems(
            effective_enabled=state_after.enabled,
            provenance=state_after.source,
            desired_enabled=enabled,
        )
        return GuardedFlipOutcome(
            state=state_after,
            refusals=problems,
            needs_human=bool(problems) or decision.needs_human,
            needs_human_reasons=decision.needs_human_reasons,
            applied=not problems,
            write_attempted=True,
            **base,
        )
