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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from platform_control.errors import BlueprintTemplateNotEnabledError, NotFoundError
from platform_control.models.blueprint_template_override import BlueprintTemplateOverride
from platform_control.services.source_blueprints import is_source_blueprint_default_enabled


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
            raise BlueprintTemplateNotEnabledError(
                f"Blueprint template '{overlay_id}/{provider_template_id}' is not enabled for "
                "live acquisition. Capture acceptance-run evidence, then turn the config key on "
                "from the admin panel's Blueprints inventory (ADR-0030, #632, #668)."
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
