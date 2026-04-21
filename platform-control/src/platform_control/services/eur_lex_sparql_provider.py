"""EUR-Lex SPARQL acquisition provider.

Resolves a seed ELI URI (e.g. `http://data.europa.eu/eli/reg/2016/679/oj`
for GDPR) into an HTML manifestation via the EUR-Lex Cellar SPARQL
endpoint. Mirrors the Fedlex SPARQL provider's work → expression →
manifestation flow, but uses the CDM (Common Data Model) ontology
instead of jolux.

Two-key production lock:
- `live_ready = True` here means the code is internally consistent and
  mocked tests cover the logic. Templates referencing this provider
  are still gated by `enabled: false` in
  `source_blueprints.yaml` until an operator captures a live acceptance
  run (see `docs/runbooks/eu-eur-lex-fast-loop-backlog.md` for the
  GDPR and Copyright-Directive smoke targets).

Language selection uses the EUR-Lex authority-list mapping between
ISO 639-1 codes and three-letter ISO 639-2 uppercase codes on
`publications.europa.eu/resource/authority/language/*`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from platform_control.domain import AcquisitionProvider
from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    ProviderPlan,
    ProviderResource,
    ProviderStartResult,
)

_EUR_LEX_SPARQL_ENDPOINT = "http://publications.europa.eu/webapi/rdf/sparql"
_EUR_LEX_CELLAR_HOST = "publications.europa.eu"
_EUR_LEX_DATA_HOST = "data.europa.eu"
_EUR_LEX_LANGUAGE_AUTHORITY = "http://publications.europa.eu/resource/authority/language/"
_EUR_LEX_FILE_TYPE_AUTHORITY = "http://publications.europa.eu/resource/authority/file-type/"

# ISO 639-1 → EUR-Lex 3-letter authority language code.
# Evidara-relevant subset; extend as needed.
_ISO_639_1_TO_AUTHORITY: dict[str, str] = {
    "bg": "BUL",
    "cs": "CES",
    "da": "DAN",
    "de": "DEU",
    "el": "ELL",
    "en": "ENG",
    "es": "SPA",
    "et": "EST",
    "fi": "FIN",
    "fr": "FRA",
    "ga": "GLE",
    "hr": "HRV",
    "hu": "HUN",
    "it": "ITA",
    "lt": "LIT",
    "lv": "LAV",
    "mt": "MLT",
    "nl": "NLD",
    "pl": "POL",
    "pt": "POR",
    "ro": "RON",
    "sk": "SLK",
    "sl": "SLV",
    "sv": "SWE",
}


class EurLexSparqlProvider:
    """EUR-Lex SPARQL provider.

    Implements the work → expression → manifestation flow used by EUR-Lex
    when resolving an ELI URI. Queries run against the public SPARQL
    endpoint at `publications.europa.eu/webapi/rdf/sparql`; a text
    manifestation (HTML preferred) is fetched from Cellar at the end.
    """

    provider_name = AcquisitionProvider.EUR_LEX_SPARQL.value
    live_ready = True

    _RESOLVE_ELI_QUERY = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?cellar_uri
WHERE {{
  ?cellar_uri owl:sameAs <{eli_uri}> .
  FILTER(STRSTARTS(STR(?cellar_uri), "http://publications.europa.eu/resource/cellar/"))
}}
LIMIT 1
""".strip()

    _RESOLVE_ELI_CELEX_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?work
WHERE {{
  ?work cdm:resource_legal_id_celex '{celex}'^^<http://www.w3.org/2001/XMLSchema#string> .
}}
LIMIT 1
""".strip()

    _EXPRESSION_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?expression ?language ?celex
WHERE {{
  ?expression cdm:expression_belongs_to_work <{work_uri}> .
  ?expression cdm:expression_uses_language ?language .
  OPTIONAL {{ <{work_uri}> cdm:resource_legal_id_celex ?celex . }}
}}
""".strip()

    _MANIFESTATION_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?manifestation ?format
WHERE {{
  ?manifestation cdm:manifestation_manifests_expression <{expression_uri}> .
  ?manifestation cdm:manifestation_type ?format .
}}
""".strip()

    _TITLE_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?title
WHERE {{
  <{expression_uri}> cdm:expression_title ?title .
}}
LIMIT 1
""".strip()

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source
        acquisition_spec: dict[str, Any] = source_version.acquisition_spec or {}
        work_uris = self._seed_work_uris(acquisition_spec)
        sparql_endpoint = self._validate_eurlex_url(
            str(acquisition_spec.get("sparql_endpoint") or _EUR_LEX_SPARQL_ENDPOINT)
        )
        preferred_languages = self._preferred_languages(acquisition_spec)
        max_expressions = int(acquisition_spec.get("max_expressions") or 1)
        timeout_seconds = float(acquisition_spec.get("request_timeout_seconds") or 30.0)
        max_content_bytes = int(acquisition_spec.get("max_content_bytes") or 2_000_000)

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []

        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            for work_uri in work_uris:
                original_uri = work_uri
                try:
                    # Resolve ELI URI to Cellar URI if needed.
                    if self._looks_like_eli(work_uri):
                        cellar_uri = await self._resolve_eli_to_cellar(
                            client=client,
                            sparql_endpoint=sparql_endpoint,
                            eli_uri=work_uri,
                        )
                        if cellar_uri is None:
                            failures.append(
                                {"url": work_uri, "error": "could not resolve ELI to Cellar URI"}
                            )
                            continue
                        work_uri = cellar_uri

                    expression_bindings = await self._query_expressions(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=work_uri,
                    )
                    if not expression_bindings:
                        failures.append(
                            {"url": work_uri, "error": "no expressions returned by SPARQL"}
                        )
                        continue
                    selected = self._select_expressions(
                        bindings=expression_bindings,
                        preferred_languages=preferred_languages,
                        max_expressions=max_expressions,
                    )
                    if not selected:
                        failures.append(
                            {
                                "url": work_uri,
                                "error": (
                                    "no expression matched preferred languages "
                                    f"{preferred_languages}"
                                ),
                            }
                        )
                        continue
                    celex = next(
                        (b["celex"] for b in expression_bindings if b.get("celex")),
                        None,
                    )
                    for pick in selected:
                        expression_uri = pick["expression"]
                        language_iri = pick.get("language")
                        iso_language = (
                            self._language_iri_to_iso(language_iri) if language_iri else None
                        )
                        manifestation_url = await self._pick_html_manifestation(
                            client=client,
                            sparql_endpoint=sparql_endpoint,
                            expression_uri=expression_uri,
                        )
                        if manifestation_url is None:
                            failures.append(
                                {
                                    "url": expression_uri,
                                    "error": "no HTML manifestation found",
                                }
                            )
                            continue
                        title = await self._query_title(
                            client=client,
                            sparql_endpoint=sparql_endpoint,
                            expression_uri=expression_uri,
                        )
                        resolved_url, response, body = await self._fetch_text_manifestation(
                            client=client,
                            url=manifestation_url,
                            max_content_bytes=max_content_bytes,
                        )
                        content_type = (
                            response.headers.get("content-type", "text/html")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        charset = response.charset_encoding or "utf-8"
                        if not body:
                            failures.append(
                                {
                                    "url": manifestation_url,
                                    "error": "manifestation fetch returned empty body",
                                }
                            )
                            continue
                        body_text = body.decode(charset, errors="replace")
                        resources.append(
                            ProviderResource(
                                source_url=original_uri,
                                final_url=resolved_url,
                                content_type=content_type,
                                body=body_text,
                                title=title or expression_uri.rsplit("/", 1)[-1],
                                http_status=response.status_code,
                                discovery_depth=0,
                                metadata={
                                    "provider": self.provider_name,
                                    "sparql_endpoint": sparql_endpoint,
                                    "expression_uri": expression_uri,
                                    "manifestation_url": resolved_url,
                                    "language_iri": language_iri,
                                    "language": iso_language,
                                    "eli_uri": (
                                        original_uri if self._looks_like_eli(original_uri) else None
                                    ),
                                    "celex": celex,
                                    "fetched_at": datetime.now(UTC).isoformat(),
                                },
                            )
                        )
                except Exception as exc:  # pragma: no cover - defensive capture path
                    failures.append({"url": work_uri, "error": str(exc)})

        response_payload = {
            "provider": self.provider_name,
            "requested": len(work_uris),
            "captured": len(resources),
            "failed": len(failures),
            "failures": failures,
        }
        inline_failure_reason = None
        if not resources:
            inline_failure_reason = "EUR-Lex SPARQL provider did not capture any resources."

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"eurlexsparql_{run.run_id}",
            request_payload={
                "work_uris": work_uris,
                "preferred_languages": preferred_languages,
                "manifestation_format": "html",
                "max_expressions": max_expressions,
            },
            response_payload=response_payload,
            inline_resources=resources,
            inline_failure_reason=inline_failure_reason,
        )

    def plan(self, source: Source, source_version: SourceVersion) -> ProviderPlan:
        """Describe the acquisition without network IO."""
        del source
        acquisition_spec: dict[str, Any] = source_version.acquisition_spec or {}
        try:
            work_uris = self._seed_work_uris(acquisition_spec)
        except ProviderConfigurationError:
            work_uris = []
        preferred_languages = self._preferred_languages(acquisition_spec)
        notes: list[str] = []
        if preferred_languages:
            notes.append(f"preferred_languages={preferred_languages}")
        return ProviderPlan(
            provider=self.provider_name,
            mode="work_to_expression",
            seed_urls=work_uris,
            estimated_request_count=len(work_uris),
            request_timeout_seconds=float(acquisition_spec.get("request_timeout_seconds") or 30.0),
            notes=notes,
            raw=dict(acquisition_spec),
        )

    # ─── Helpers ──────────────────────────────────────────────

    def _seed_work_uris(self, acquisition_spec: dict[str, Any]) -> list[str]:
        raw = acquisition_spec.get("seed_urls") or acquisition_spec.get("seed_url")
        if isinstance(raw, str):
            return [self._validate_eurlex_eli(raw)]
        if isinstance(raw, list):
            return [self._validate_eurlex_eli(str(item)) for item in raw if isinstance(item, str)]
        raise ProviderConfigurationError(
            "eur_lex_sparql requires acquisition_spec.seed_url or seed_urls"
        )

    @staticmethod
    def _preferred_languages(acquisition_spec: dict[str, Any] | None) -> list[str]:
        if not acquisition_spec:
            return ["en"]
        raw = acquisition_spec.get("preferred_languages") or ["en"]
        return [
            str(code).strip().lower() for code in raw if isinstance(code, str) and str(code).strip()
        ]

    def _language_iri_for_iso(self, iso_code: str) -> str | None:
        authority = _ISO_639_1_TO_AUTHORITY.get(iso_code.lower())
        if authority is None:
            return None
        return f"{_EUR_LEX_LANGUAGE_AUTHORITY}{authority}"

    def _language_iri_to_iso(self, iri: str) -> str | None:
        if not isinstance(iri, str) or not iri.startswith(_EUR_LEX_LANGUAGE_AUTHORITY):
            return None
        authority = iri[len(_EUR_LEX_LANGUAGE_AUTHORITY) :].upper()
        for iso, code in _ISO_639_1_TO_AUTHORITY.items():
            if code == authority:
                return iso
        return None

    def _select_expressions(
        self,
        *,
        bindings: list[dict[str, Any]],
        preferred_languages: list[str],
        max_expressions: int,
    ) -> list[dict[str, Any]]:
        """Rank expression bindings by preferred-language index; take top N."""
        target_iris = {
            self._language_iri_for_iso(code)
            for code in preferred_languages
            if self._language_iri_for_iso(code)
        }
        ranked: list[tuple[int, dict[str, Any]]] = []
        for binding in bindings:
            lang_iri = binding.get("language")
            if lang_iri in target_iris:
                # Prefer the earliest preferred_language that matched.
                iso = self._language_iri_to_iso(lang_iri) if lang_iri else None
                if iso is not None and iso in preferred_languages:
                    ranked.append((preferred_languages.index(iso), binding))
        ranked.sort(key=lambda pair: pair[0])
        return [binding for _, binding in ranked[: max(1, max_expressions)]]

    async def _resolve_eli_to_cellar(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        eli_uri: str,
    ) -> str | None:
        # The SPARQL endpoint stores sameAs as <cellar> owl:sameAs <pub-eli>,
        # where the ELI host is publications.europa.eu (not data.europa.eu).
        # Try the publications.europa.eu variant first.
        pub_eli = eli_uri.replace(
            "http://data.europa.eu/eli/",
            "http://publications.europa.eu/resource/eli/",
        )
        for candidate in [pub_eli, eli_uri]:
            response = await client.get(
                sparql_endpoint,
                params={
                    "query": self._RESOLVE_ELI_QUERY.format(eli_uri=candidate),
                    "format": "application/sparql-results+json",
                },
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()
            bindings = response.json().get("results", {}).get("bindings", [])
            if bindings:
                return bindings[0].get("cellar_uri", {}).get("value")
        return None

    async def _query_expressions(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
    ) -> list[dict[str, Any]]:
        response = await client.get(
            sparql_endpoint,
            params={
                "query": self._EXPRESSION_QUERY.format(work_uri=work_uri),
                "format": "application/sparql-results+json",
            },
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        payload = response.json()
        bindings = payload.get("results", {}).get("bindings", [])
        parsed: list[dict[str, Any]] = []
        for binding in bindings:
            expression = binding.get("expression", {}).get("value")
            language = binding.get("language", {}).get("value")
            celex = binding.get("celex", {}).get("value")
            if isinstance(expression, str):
                parsed.append({"expression": expression, "language": language, "celex": celex})
        return parsed

    async def _pick_html_manifestation(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        expression_uri: str,
    ) -> str | None:
        response = await client.get(
            sparql_endpoint,
            params={
                "query": self._MANIFESTATION_QUERY.format(expression_uri=expression_uri),
                "format": "application/sparql-results+json",
            },
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        payload = response.json()
        bindings = payload.get("results", {}).get("bindings", [])
        # Prefer HTML; fall back to XHTML; skip PDFs (binary) in this scaffold.
        # The format value may be a full authority IRI or a short label (e.g. "xhtml").
        html_iri = f"{_EUR_LEX_FILE_TYPE_AUTHORITY}HTML"
        xhtml_iri = f"{_EUR_LEX_FILE_TYPE_AUTHORITY}XHTML"
        preferred = [html_iri, xhtml_iri, "html", "xhtml"]
        best_url: str | None = None
        best_rank = len(preferred)
        for binding in bindings:
            manifestation = binding.get("manifestation", {}).get("value")
            fmt = binding.get("format", {}).get("value")
            if not isinstance(manifestation, str) or not isinstance(fmt, str):
                continue
            fmt_lower = fmt.lower()
            for rank, candidate in enumerate(preferred):
                if fmt == candidate or fmt_lower == candidate:
                    if rank < best_rank:
                        best_rank = rank
                        best_url = manifestation
                    break
        return best_url

    async def _query_title(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        expression_uri: str,
    ) -> str | None:
        response = await client.get(
            sparql_endpoint,
            params={
                "query": self._TITLE_QUERY.format(expression_uri=expression_uri),
                "format": "application/sparql-results+json",
            },
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        payload = response.json()
        bindings = payload.get("results", {}).get("bindings", [])
        for binding in bindings:
            title = binding.get("title", {}).get("value")
            if isinstance(title, str) and title.strip():
                return title.strip()
        return None

    async def _fetch_text_manifestation(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
        max_content_bytes: int,
    ) -> tuple[str, httpx.Response, bytes]:
        response = await client.get(
            url,
            headers={"Accept": "application/xhtml+xml, text/html;q=0.9, */*;q=0.1"},
        )
        response.raise_for_status()
        body = await self._read_body_limited(response, max_content_bytes)
        return str(response.url), response, body

    async def _read_body_limited(self, response: httpx.Response, max_bytes: int) -> bytes:
        body = response.content or b""
        if len(body) > max_bytes:
            body = body[:max_bytes]
        return body

    @staticmethod
    def _looks_like_eli(uri: str) -> bool:
        parsed = urlparse(uri)
        return parsed.netloc == _EUR_LEX_DATA_HOST and parsed.path.startswith("/eli/")

    def _validate_eurlex_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ProviderConfigurationError(f"unsupported URL scheme for EUR-Lex: {url}")
        if parsed.netloc not in {_EUR_LEX_CELLAR_HOST, _EUR_LEX_DATA_HOST}:
            raise ProviderConfigurationError(f"unsupported host for EUR-Lex SPARQL endpoint: {url}")
        return url

    def _validate_eurlex_eli(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ProviderConfigurationError(f"unsupported URL scheme for EUR-Lex seed: {url}")
        if parsed.netloc != _EUR_LEX_DATA_HOST:
            raise ProviderConfigurationError(
                f"EUR-Lex seed URL must use host {_EUR_LEX_DATA_HOST}, got: {url}"
            )
        if not parsed.path.startswith("/eli/"):
            raise ProviderConfigurationError(
                f"EUR-Lex seed URL must be an ELI URI (path starts with /eli/): {url}"
            )
        return url
