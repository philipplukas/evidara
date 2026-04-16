from __future__ import annotations

from platform_control.config import Settings
from platform_control.services.bundesland_http_provider import BundeslandHttpProvider
from platform_control.services.deterministic_http_provider import DeterministicHttpProvider
from platform_control.services.eur_lex_sparql_provider import EurLexSparqlProvider
from platform_control.services.fedlex_sparql_provider import FedlexSparqlProvider
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.regione_http_provider import RegioneHttpProvider
from platform_control.services.ris_ogd_provider import RisOgdProvider


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FirecrawlProvider(settings))
    registry.register(DeterministicHttpProvider())
    registry.register(FedlexSparqlProvider())
    registry.register(RisOgdProvider())
    # Sub-federal and supranational scaffolds: registered so templates can
    # reference the provider names, but each raises NotImplementedError on
    # start_run until its live adapter lands.
    registry.register(EurLexSparqlProvider())
    registry.register(BundeslandHttpProvider())
    registry.register(RegioneHttpProvider())
    return registry
