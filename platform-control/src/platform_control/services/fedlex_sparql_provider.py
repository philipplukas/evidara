from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from platform_control.domain import AcquisitionProvider
from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    ProviderResource,
    ProviderStartResult,
)

_FEDLEX_HOST = "fedlex.data.admin.ch"
_TITLE_PATTERN = re.compile(r'jolux:title\s+"([^"]+)"')
_TITLE_SHORT_PATTERN = re.compile(r'jolux:titleShort\s+"([^"]+)"')


class FedlexSparqlProvider:
    provider_name = AcquisitionProvider.FEDLEX_SPARQL.value
    _EXPRESSION_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?expr
WHERE {{
  <{work_uri}> jolux:isRealizedBy ?expr .
}}
ORDER BY ?expr
""".strip()

    _TITLE_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?title ?titleShort
WHERE {{
  <{expression_uri}> jolux:title ?title .
  OPTIONAL {{ <{expression_uri}> jolux:titleShort ?titleShort . }}
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
        acquisition_spec = source_version.acquisition_spec or {}
        work_uris = self._seed_work_uris(acquisition_spec)
        sparql_endpoint = self._validate_fedlex_url(
            str(acquisition_spec.get("sparql_endpoint") or f"https://{_FEDLEX_HOST}/sparqlendpoint")
        )
        preferred_languages = self._preferred_languages(acquisition_spec)
        max_expressions = int(acquisition_spec.get("max_expressions") or 1)
        timeout_seconds = float(acquisition_spec.get("request_timeout_seconds") or 30.0)
        max_content_bytes = int(acquisition_spec.get("max_content_bytes") or 2_000_000)

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []

        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            for work_uri in work_uris:
                try:
                    expression_uris = await self._query_expression_uris(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=work_uri,
                    )
                    selected_expression_uris = self._select_expression_uris(
                        expression_uris=expression_uris,
                        preferred_languages=preferred_languages,
                        max_expressions=max_expressions,
                    )
                    describe_turtle = await self._describe_graph(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=work_uri,
                        expression_uris=selected_expression_uris,
                        max_content_bytes=max_content_bytes,
                    )
                    title, title_short = await self._query_title(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        expression_uris=selected_expression_uris,
                    )
                    body = json.dumps(
                        {
                            "provider": self.provider_name,
                            "work_uri": work_uri,
                            "sparql_endpoint": sparql_endpoint,
                            "preferred_languages": preferred_languages,
                            "expression_uris": selected_expression_uris,
                            "title": title,
                            "title_short": title_short,
                            "describe_turtle": describe_turtle,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    resources.append(
                        ProviderResource(
                            source_url=work_uri,
                            final_url=work_uri,
                            content_type="application/json",
                            body=body,
                            title=title or title_short or work_uri.rsplit("/", 1)[-1],
                            http_status=200,
                            discovery_depth=0,
                            metadata={
                                "provider": self.provider_name,
                                "sparql_endpoint": sparql_endpoint,
                                "expression_uris": selected_expression_uris,
                                "title_short": title_short,
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
            inline_failure_reason = "Fedlex SPARQL provider did not capture any resources."

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"fedlexsparql_{run.run_id}",
            request_payload={
                "work_uris": work_uris,
                "sparql_endpoint": sparql_endpoint,
                "preferred_languages": preferred_languages,
                "max_expressions": max_expressions,
            },
            response_payload=response_payload,
            inline_resources=resources,
            inline_failure_reason=inline_failure_reason,
        )

    def _seed_work_uris(self, acquisition_spec: dict[str, object]) -> list[str]:
        seed_urls = [
            str(url)
            for url in acquisition_spec.get("seed_urls", [])
            if isinstance(url, str) and url.strip()
        ]
        seed_url = acquisition_spec.get("seed_url")
        if isinstance(seed_url, str) and seed_url.strip():
            seed_urls.append(seed_url)

        unique_uris: list[str] = []
        seen: set[str] = set()
        for url in seed_urls:
            validated = self._validate_fedlex_url(url)
            if validated in seen:
                continue
            unique_uris.append(validated)
            seen.add(validated)
        if not unique_uris:
            raise ProviderConfigurationError(
                "fedlex_sparql provider requires acquisition_spec.seed_url or seed_urls."
            )
        return unique_uris

    def _preferred_languages(self, acquisition_spec: dict[str, object]) -> list[str]:
        raw = acquisition_spec.get("preferred_languages")
        if isinstance(raw, list):
            languages = [str(item).strip().lower() for item in raw if str(item).strip()]
        else:
            fallback = acquisition_spec.get("language_codes")
            languages = [str(item).strip().lower()[:2] for item in fallback or [] if str(item).strip()]
        return [language for language in languages if language]

    async def _query_expression_uris(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
    ) -> list[str]:
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
        expression_uris: list[str] = []
        for binding in bindings:
            expr = binding.get("expr", {}).get("value")
            if isinstance(expr, str) and expr.startswith(f"https://{_FEDLEX_HOST}/"):
                expression_uris.append(expr)
        return expression_uris

    def _select_expression_uris(
        self,
        *,
        expression_uris: list[str],
        preferred_languages: list[str],
        max_expressions: int,
    ) -> list[str]:
        if not expression_uris:
            return []
        if preferred_languages:
            preferred_matches = [
                expr
                for language in preferred_languages
                for expr in expression_uris
                if expr.rstrip("/").endswith(f"/{language}")
            ]
            deduped = list(dict.fromkeys(preferred_matches))
            if deduped:
                return deduped[:max_expressions]
        return expression_uris[:max_expressions]

    async def _describe_graph(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
        expression_uris: list[str],
        max_content_bytes: int,
    ) -> str:
        targets = " ".join(f"<{uri}>" for uri in [work_uri, *expression_uris])
        query = f"DESCRIBE {targets}"
        response = await client.get(
            sparql_endpoint,
            params={"query": query},
            headers={"Accept": "text/turtle"},
        )
        response.raise_for_status()
        body = await self._read_body_limited(response=response, max_content_bytes=max_content_bytes)
        if body is None:
            raise ProviderConfigurationError(
                f"fedlex_sparql response exceeded max_content_bytes={max_content_bytes}"
            )
        return body.decode(response.charset_encoding or "utf-8", errors="replace")

    async def _query_title(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        expression_uris: list[str],
    ) -> tuple[str | None, str | None]:
        for expression_uri in expression_uris:
            response = await client.get(
                sparql_endpoint,
                params={
                    "query": self._TITLE_QUERY.format(expression_uri=expression_uri),
                    "format": "application/sparql-results+json",
                },
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()
            bindings = response.json().get("results", {}).get("bindings", [])
            if bindings:
                row = bindings[0]
                title = row.get("title", {}).get("value")
                title_short = row.get("titleShort", {}).get("value")
                return (
                    title if isinstance(title, str) else None,
                    title_short if isinstance(title_short, str) else None,
                )
        return None, None

    async def _read_body_limited(
        self,
        *,
        response: httpx.Response,
        max_content_bytes: int,
    ) -> bytes | None:
        collected = bytearray()
        async for chunk in response.aiter_bytes():
            collected.extend(chunk)
            if len(collected) > max_content_bytes:
                return None
        return bytes(collected)

    def _validate_fedlex_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != _FEDLEX_HOST:
            raise ProviderConfigurationError(
                f"fedlex_sparql provider only supports https://{_FEDLEX_HOST} URLs: {url}"
            )
        return url
