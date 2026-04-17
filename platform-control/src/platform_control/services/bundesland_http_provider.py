"""DE Bundesland HTTP acquisition provider.

Each Bundesland publishes legal content on its own portal. This provider
is a thin config-driven multi-tenant adapter: the blueprint template
carries the ISO 3166-2:DE code plus seed URLs, and the base class
handles fetching, title extraction, and resource emission. The first
target is Bayern (`DE-BY`) with seed URLs on `gesetze-bayern.de`;
other Länder fall in as operators add seed URLs and run acceptance
tests.

See `PortalHttpProviderBase` for the shared acquisition flow. See
T2.1 decision in
`docs/runbooks/country-rollout-drift-prevention-backlog.md` for the
per-portal-vs-multi-tenant rationale.
"""

from __future__ import annotations

from platform_control.domain import AcquisitionProvider
from platform_control.services.portal_http_provider_base import (
    PortalHttpProviderBase,
)


class BundeslandHttpProvider(PortalHttpProviderBase):
    """Config-driven multi-tenant HTTP provider for DE Bundesländer."""

    provider_name = AcquisitionProvider.BUNDESLAND_HTTP.value
    subdivision_spec_key = "bundesland"
    subdivision_country = "DE"
    live_ready = True
    supported_portals: dict[str, str] = {
        # ISO 3166-2:DE code → portal host. Seed URLs in each blueprint
        # template must resolve to the matching host (or a subdomain of
        # it); the base class enforces the allow-list.
        "DE-BY": "www.gesetze-bayern.de",
        "DE-NW": "recht.nrw.de",
        "DE-BW": "www.landesrecht-bw.de",
        "DE-BE": "gesetze.berlin.de",
        "DE-HH": "www.landesrecht-hamburg.de",
        # Remaining Länder land as operators add seed URLs and run
        # per-state acceptance tests.
    }
