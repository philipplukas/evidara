from __future__ import annotations

from platform_control.config import Settings
from platform_control.services.cassette_provider import CassetteProvider
from platform_control.services.deterministic_http_provider import DeterministicHttpProvider
from platform_control.services.fedlex_sparql_provider import FedlexSparqlProvider
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.ris_ogd_provider import RisOgdProvider


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FirecrawlProvider(settings))
    registry.register(DeterministicHttpProvider())
    registry.register(FedlexSparqlProvider())
    registry.register(RisOgdProvider())
    registry.register(CassetteProvider(cassette_dir=settings.cassette_dir))
    return registry
