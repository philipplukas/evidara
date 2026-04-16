"""EUR-Lex SPARQL acquisition provider (scaffold).

This provider is a scaffold. It does not yet perform any network calls
against the EUR-Lex SPARQL endpoint (`http://publications.europa.eu/webapi/rdf/sparql`)
or resolve ELI URIs. `start_run` raises `NotImplementedError` with a pointer
to the follow-up ticket.

Intentional symmetry with `fedlex_sparql_provider.py`:
  - shared dataclasses (`ProviderResource`, `ProviderStartResult`)
  - work → expression → manifestation resolution shape
  - per-language selection on `acquisition_spec.preferred_languages`

See docs/runbooks/eu-eur-lex-fast-loop-backlog.md for the planned
execution shape and the list of known-good smoke documents (GDPR = CELEX
`32016R0679`, Directive on copyright in the Digital Single Market = CELEX
`32019L0790`) we will anchor the first live run against.
"""

from __future__ import annotations

from typing import Any

from platform_control.domain import AcquisitionProvider
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import ProviderStartResult

_EUR_LEX_SPARQL_ENDPOINT = "http://publications.europa.eu/webapi/rdf/sparql"
_EUR_LEX_ELI_BASE = "http://data.europa.eu/eli/"


class EurLexSparqlProvider:
    """EUR-Lex SPARQL provider scaffold.

    The live implementation will:
      1. Resolve a seed ELI URI (regulation / directive) to its work node.
      2. Enumerate `?expr cdm:work_has_expression ?expr` for each language.
      3. Pick the best expression per `acquisition_spec.preferred_languages`.
      4. For each picked expression, fetch the HTML / PDF manifestation
         via the Cellar endpoint.
      5. Emit `ProviderResource` entries matching the canonical shape used
         by the Fedlex SPARQL provider.
    """

    provider_name = AcquisitionProvider.EUR_LEX_SPARQL.value
    live_ready = False

    _WORK_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?work
WHERE {{
  <{eli_uri}> cdm:resource_legal_id_celex ?celex .
  ?work cdm:resource_legal_id_celex ?celex .
}}
LIMIT 1
""".strip()

    _EXPRESSION_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?expression ?language
WHERE {{
  <{work_uri}> cdm:work_has_expression ?expression .
  ?expression cdm:expression_uses_language ?language .
}}
""".strip()

    _MANIFESTATION_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?manifestation ?format
WHERE {{
  <{expression_uri}> cdm:expression_manifested_by_manifestation ?manifestation .
  ?manifestation cdm:manifestation_type ?format .
}}
""".strip()

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source, source_version, run
        raise NotImplementedError(
            "EurLexSparqlProvider is a scaffold. Live SPARQL fetch lands in "
            "the follow-up ticket tracked by "
            "docs/runbooks/eu-eur-lex-fast-loop-backlog.md."
        )

    @staticmethod
    def _preferred_languages(acquisition_spec: dict[str, Any] | None) -> list[str]:
        """Return the ordered list of preferred language codes, defaulting to English first."""
        if not acquisition_spec:
            return ["en"]
        raw = acquisition_spec.get("preferred_languages") or ["en"]
        return [str(code).lower() for code in raw if isinstance(code, str)]
