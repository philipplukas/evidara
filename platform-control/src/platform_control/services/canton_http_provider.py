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

The provider ships DISABLED — `readiness = AcquisitionReadiness.SCAFFOLD`
on the class below, not the retired `live_ready=False` bool this docstring
used to name (#743). Its blueprint templates parse but the two-key lock
rejects runs of *every* mode until the portal problem below is solved; a
SCAFFOLD needs engineering, not an acceptance run. The portal hosts below
are placeholder-but-plausible and MUST be verified against the real
cantonal portals at live-enablement.

Readiness stays SCAFFOLD for a second, concrete reason (#631): several
cantonal collections — ZH-Lex among them — are JavaScript SPA portals.
Deterministic HTTP fetches only their navigation shell, not the statute,
so acquiring cantonal law from them needs SPA rendering or an underlying
data endpoint that this provider does not yet have. Until then the shared
legal-text density gate in `PortalHttpProviderBase` refuses the nav shell
(captured=0 + reason) rather than reporting a clean success on chrome.

See `PortalHttpProviderBase` for the shared acquisition flow.
"""

from __future__ import annotations

from platform_control.domain import AcquisitionProvider
from platform_control.services.acquisition_provider import AcquisitionReadiness
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
    readiness = AcquisitionReadiness.SCAFFOLD
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
