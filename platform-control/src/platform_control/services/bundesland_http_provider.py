"""DE Bundesland HTTP acquisition provider (scaffold).

Federal German law already uses `deterministic_http_bundesrecht`. Each
Bundesland has its own legal-information portal with its own URL shape
(`gesetze-bayern.de`, `recht.nrw.de`, `recht.sachsen.de`, …). Rather
than ship one provider per state, this provider is multi-tenant: the
`acquisition_spec.bundesland` field (ISO 3166-2 code, e.g. `DE-BY`)
selects the per-state adapter.

Today only Bayern (`DE-BY`) has a template in
`platform-control/src/platform_control/hierarchies/source_blueprints.yaml`.
`start_run` raises `NotImplementedError` for all codes; the live
adapters land with their individual acceptance runs.
"""

from __future__ import annotations

from typing import Any

from platform_control.domain import AcquisitionProvider
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import ProviderStartResult

_SUPPORTED_BUNDESLAENDER: dict[str, str] = {
    # ISO 3166-2:DE code → public portal base URL.
    "DE-BY": "https://www.gesetze-bayern.de/",
    "DE-NW": "https://recht.nrw.de/",
    "DE-BW": "https://www.landesrecht-bw.de/",
    "DE-BE": "https://gesetze.berlin.de/",
    "DE-HH": "https://www.landesrecht-hamburg.de/",
    # Remaining Länder stubbed out; land templates alongside each live run.
}


class BundeslandHttpProvider:
    """Multi-tenant HTTP provider for DE Bundesländer."""

    provider_name = AcquisitionProvider.BUNDESLAND_HTTP.value
    live_ready = False

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source, run
        acquisition_spec: dict[str, Any] = source_version.acquisition_spec or {}
        code = str(acquisition_spec.get("bundesland") or "").upper()
        if code not in _SUPPORTED_BUNDESLAENDER:
            raise NotImplementedError(
                f"BundeslandHttpProvider has no adapter for bundesland={code!r}. "
                f"Supported: {sorted(_SUPPORTED_BUNDESLAENDER)}."
            )
        raise NotImplementedError(
            "BundeslandHttpProvider is a scaffold. Live adapter for "
            f"{code} ({_SUPPORTED_BUNDESLAENDER[code]}) lands in the follow-up "
            "ticket alongside its first acceptance run."
        )
