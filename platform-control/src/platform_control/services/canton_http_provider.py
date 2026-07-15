"""CH canton HTTP acquisition provider.

Each Swiss canton publishes its cantonal legislation (systematische
Rechtssammlung / recueil systématique) on its own portal. This provider
is a thin config-driven multi-tenant adapter: the blueprint template
carries the ISO 3166-2:CH code plus seed URLs, and the base class
handles fetching, title extraction, and resource emission.

This is DISTINCT from the Fedlex cantonal-concordat discovery path
(federal `fedlex_sparql` in cantonal-discovery mode): this provider
scrapes each canton's *own* legislation portal, which surfaces the bulk
of cantonal/"state" legislation not mirrored on Fedlex.

The provider ships DISABLED (`live_ready=False`), so its blueprint
templates parse but the two-key lock rejects live runs until an operator
captures acceptance-run evidence per canton. The portal hosts below are
placeholder-but-plausible and MUST be verified against the real cantonal
portals at live-enablement.

See `PortalHttpProviderBase` for the shared acquisition flow.
"""

from __future__ import annotations

from platform_control.domain import AcquisitionProvider
from platform_control.services.portal_http_provider_base import (
    PortalHttpProviderBase,
)


class CantonHttpProvider(PortalHttpProviderBase):
    """Config-driven multi-tenant HTTP provider for CH cantons."""

    provider_name = AcquisitionProvider.CANTON_HTTP.value
    subdivision_spec_key = "canton_code"
    subdivision_country = "CH"
    # Scaffold: templates stay `enabled: false` and live runs are rejected
    # until an operator captures per-canton acceptance-run evidence.
    live_ready = False
    supported_portals: dict[str, str] = {
        # ISO 3166-2:CH code → cantonal legislation portal host. Seed URLs
        # in each blueprint template must resolve to the matching host (or a
        # subdomain of it); the base class enforces the allow-list.
        #
        # NOTE: exact portal hosts/paths are placeholder-but-plausible and
        # need verification against the real cantonal portals at
        # live-enablement (the systematic collections are frequently served
        # from vendor subdomains that change over time).
        "CH-ZH": "www.zh.ch",  # Zürich — zhlex systematische Sammlung
        "CH-BE": "www.belex.sites.be.ch",  # Bern — BELEX
        "CH-BS": "www.gesetzessammlung.bs.ch",  # Basel-Stadt
        # Remaining cantons land as operators add seed URLs and run
        # per-canton acceptance tests.
    }
