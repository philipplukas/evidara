"""IT regione HTTP acquisition provider.

Each Italian regione publishes regional law on its own portal. This
provider is a thin config-driven multi-tenant adapter: the blueprint
template carries the ISO 3166-2:IT code plus seed URLs, and the base
class handles fetching, title extraction, and resource emission. The
first target is Lombardia (`IT-25`) with seed URLs on
`normelombardia.consiglio.regione.lombardia.it`; other regioni fall in
as operators add seed URLs and run acceptance tests.

See `PortalHttpProviderBase` for the shared acquisition flow.
"""

from __future__ import annotations

from platform_control.domain import AcquisitionProvider
from platform_control.services.portal_http_provider_base import (
    PortalHttpProviderBase,
)


class RegioneHttpProvider(PortalHttpProviderBase):
    """Config-driven multi-tenant HTTP provider for IT regioni."""

    provider_name = AcquisitionProvider.REGIONE_HTTP.value
    subdivision_spec_key = "regione"
    subdivision_country = "IT"
    live_ready = True
    supported_portals: dict[str, str] = {
        # ISO 3166-2:IT code → portal host.
        "IT-25": "normelombardia.consiglio.regione.lombardia.it",
        "IT-62": "www.consiglio.regione.lazio.it",
        "IT-52": "www.consiglio.regione.toscana.it",
        "IT-21": "www.cr.piemonte.it",
        # Remaining regioni land as operators add seed URLs and run
        # per-regione acceptance tests.
    }
