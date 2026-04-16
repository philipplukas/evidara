"""IT regione HTTP acquisition provider (scaffold).

Federal Italian law lives on `normattiva.it`. Regional law lives on
per-regione portals with heterogeneous URL shapes (e.g.
`normelombardia.consiglio.regione.lombardia.it` for Lombardia,
`consiglio.regione.piemonte.it` for Piemonte). This provider is
multi-tenant: the `acquisition_spec.regione` field (ISO 3166-2:IT code,
e.g. `IT-25` for Lombardia) selects the per-regione adapter.

Today only Lombardia (`IT-25`) has a template in
`platform-control/src/platform_control/hierarchies/source_blueprints.yaml`.
`start_run` raises `NotImplementedError` for all codes; live adapters
land with their individual acceptance runs.
"""

from __future__ import annotations

from typing import Any

from platform_control.domain import AcquisitionProvider
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import ProviderStartResult

_SUPPORTED_REGIONI: dict[str, str] = {
    # ISO 3166-2:IT code → public portal base URL.
    "IT-25": "https://normelombardia.consiglio.regione.lombardia.it/",
    "IT-62": "https://www.consiglio.regione.lazio.it/",
    "IT-52": "https://www.consiglio.regione.toscana.it/",
    "IT-21": "https://www.cr.piemonte.it/",
    # Remaining regioni stubbed out; land templates alongside each live run.
}


class RegioneHttpProvider:
    """Multi-tenant HTTP provider for IT regioni."""

    provider_name = AcquisitionProvider.REGIONE_HTTP.value

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source, run
        acquisition_spec: dict[str, Any] = source_version.acquisition_spec or {}
        code = str(acquisition_spec.get("regione") or "").upper()
        if code not in _SUPPORTED_REGIONI:
            raise NotImplementedError(
                f"RegioneHttpProvider has no adapter for regione={code!r}. "
                f"Supported: {sorted(_SUPPORTED_REGIONI)}."
            )
        raise NotImplementedError(
            "RegioneHttpProvider is a scaffold. Live adapter for "
            f"{code} ({_SUPPORTED_REGIONI[code]}) lands in the follow-up "
            "ticket alongside its first acceptance run."
        )
