from __future__ import annotations

from platform_control.config import Settings
from platform_control.services.bundesland_http_provider import BundeslandHttpProvider
from platform_control.services.canton_http_provider import CantonHttpProvider
from platform_control.services.cassette_provider import CassetteProvider
from platform_control.services.ch_court_decisions_provider import ChCourtDecisionsProvider
from platform_control.services.deterministic_http_provider import DeterministicHttpProvider
from platform_control.services.eur_lex_sparql_provider import EurLexSparqlProvider
from platform_control.services.fedlex_sparql_provider import FedlexSparqlProvider
from platform_control.services.firecrawl_provider import FirecrawlProvider
from platform_control.services.gemeinde_http_provider import GemeindeHttpProvider
from platform_control.services.legifrance_provider import LegifranceProvider
from platform_control.services.provider_registry import ProviderRegistry
from platform_control.services.regione_http_provider import RegioneHttpProvider
from platform_control.services.ris_ogd_provider import RisOgdProvider


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FirecrawlProvider(settings))
    registry.register(DeterministicHttpProvider())
    registry.register(FedlexSparqlProvider())
    registry.register(RisOgdProvider())
    # Sub-federal and supranational providers: live_ready but blueprint
    # templates referencing them stay `enabled: false` until an operator
    # captures acceptance-run evidence for each jurisdiction.
    registry.register(EurLexSparqlProvider())
    registry.register(
        LegifranceProvider(
            client_id=settings.legifrance_client_id,
            client_secret=settings.legifrance_client_secret,
        )
    )
    registry.register(BundeslandHttpProvider())
    registry.register(RegioneHttpProvider())
    # Swiss federal court decisions (BGer/BVGer). Implemented and unit-tested;
    # readiness=awaiting_evidence, so the two-key lock rejects production runs
    # until an operator captures acceptance-run evidence (#530). Not a scaffold —
    # a mode=acceptance run may dispatch to produce that evidence (#743).
    registry.register(ChCourtDecisionsProvider())
    # Swiss cantonal legislation portals. A genuine scaffold
    # (readiness=scaffold): start_run is not implemented, so no run of any mode
    # dispatches. Registered only so blueprint templates referencing it parse.
    registry.register(CantonHttpProvider())
    # Swiss communal (Gemeinde) legal collections — where the ADR-0033 acceptance
    # test lives. readiness=awaiting_evidence: the PDF blockers this comment used
    # to cite have both landed (binary manifestations #590/ADR-0037, the
    # layout-aware normaliser #650/ADR-0041). What remains is acceptance evidence,
    # which a mode=acceptance run produces (#735, #743).
    registry.register(GemeindeHttpProvider())
    # Fixture-backed replay for SHADOW execution mode.
    registry.register(CassetteProvider(cassette_dir=settings.cassette_dir))
    return registry
