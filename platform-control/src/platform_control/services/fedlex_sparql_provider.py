from __future__ import annotations

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
_FEDLEX_FILESTORE_HOST = "www.fedlex.admin.ch"
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

    _MEMBER_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?member
WHERE {{
  ?member jolux:isMemberOf <{work_uri}> .
}}
ORDER BY ?member
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
                    concrete_work_uri = await self._resolve_concrete_work_uri(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=work_uri,
                    )
                    expression_uris = await self._query_expression_uris(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=concrete_work_uri,
                    )
                    selected_expression_uris = self._select_expression_uris(
                        expression_uris=expression_uris,
                        preferred_languages=preferred_languages,
                        max_expressions=max_expressions,
                    )
                    describe_turtle = await self._describe_graph(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=concrete_work_uri,
                        expression_uris=selected_expression_uris,
                        max_content_bytes=max_content_bytes,
                    )
                    title, title_short = await self._query_title(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        expression_uris=selected_expression_uris,
                    )
                    html_url = self._filestore_html_url(selected_expression_uris[0], concrete_work_uri)
                    resolved_url, response, body = await self._fetch_text_manifestation(
                        client=client,
                        url=html_url,
                        max_content_bytes=max_content_bytes,
                    )
                    content_type = response.headers.get("content-type", "text/html").split(";", 1)[0].strip().lower()
                    charset = response.charset_encoding or "utf-8"
                    if not body:
                        raise ProviderConfigurationError(
                            f"fedlex_sparql manifestation response was empty for {html_url}"
                        )
                    body_text = body.decode(charset, errors="replace")
                    html_title = self._title_from_html(body_text)
                    resources.append(
                        ProviderResource(
                            source_url=work_uri,
                            final_url=resolved_url,
                            content_type=content_type,
                            body=body_text,
                            title=title or html_title or title_short or work_uri.rsplit("/", 1)[-1],
                            http_status=response.status_code,
                            discovery_depth=0,
                            metadata={
                                "provider": self.provider_name,
                                "sparql_endpoint": sparql_endpoint,
                                "concrete_work_uri": concrete_work_uri,
                                "expression_uris": selected_expression_uris,
                                "manifestation_url": resolved_url,
                                "title_short": title_short,
                                "describe_turtle": describe_turtle,
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
                "manifestation_format": "html",
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

    async def _resolve_concrete_work_uri(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
    ) -> str:
        member_uris = await self._query_member_work_uris(
            client=client,
            sparql_endpoint=sparql_endpoint,
            work_uri=work_uri,
        )
        if member_uris:
            return member_uris[-1]
        return work_uri

    async def _query_member_work_uris(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
    ) -> list[str]:
        response = await client.get(
            sparql_endpoint,
            params={
                "query": self._MEMBER_QUERY.format(work_uri=work_uri),
                "format": "application/sparql-results+json",
            },
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        payload = response.json()
        bindings = payload.get("results", {}).get("bindings", [])
        member_uris: list[str] = []
        for binding in bindings:
            member = binding.get("member", {}).get("value")
            if isinstance(member, str) and member.startswith(f"https://{_FEDLEX_HOST}/"):
                member_uris.append(member)
        return member_uris

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
        candidate_uris: list[str] = []
        for expression_uri in expression_uris:
            candidate_uris.append(expression_uri)
            abstract_expression_uri = self._abstract_expression_uri(expression_uri)
            if abstract_expression_uri is not None:
                candidate_uris.append(abstract_expression_uri)
        for expression_uri in dict.fromkeys(candidate_uris):
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

    async def _fetch_text_manifestation(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
        max_content_bytes: int,
    ) -> tuple[str, httpx.Response, bytes]:
        response = await client.get(url, headers={"Accept": "text/html"})
        response.raise_for_status()
        body = await self._read_body_limited(response=response, max_content_bytes=max_content_bytes)
        if body is None:
            raise ProviderConfigurationError(
                f"fedlex_sparql manifestation exceeded max_content_bytes={max_content_bytes}"
            )
        return str(response.url), response, body

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

    def _filestore_html_url(self, expression_uri: str, concrete_work_uri: str) -> str:
        expression = self._validate_fedlex_url(expression_uri)
        concrete_work = self._validate_fedlex_url(concrete_work_uri)
        expression_parts = urlparse(expression).path.strip("/").split("/")
        work_parts = urlparse(concrete_work).path.strip("/").split("/")
        if len(expression_parts) < 6 or len(work_parts) < 5:
            raise ProviderConfigurationError(
                f"fedlex_sparql could not derive filestore HTML path from {expression_uri}"
            )
        path_parts = work_parts + [expression_parts[-1], "html"]
        filename = "-".join(["fedlex", "data", "admin", "ch", *path_parts]) + ".html"
        return (
            f"https://{_FEDLEX_FILESTORE_HOST}/filestore/fedlex.data.admin.ch/"
            f"{'/'.join(path_parts)}/{filename}"
        )

    def _abstract_expression_uri(self, expression_uri: str) -> str | None:
        expression = self._validate_fedlex_url(expression_uri)
        parts = urlparse(expression).path.strip("/").split("/")
        if len(parts) < 6 or not parts[-2].isdigit():
            return None
        abstract_parts = parts[:-2] + [parts[-1]]
        return f"https://{_FEDLEX_HOST}/{'/'.join(abstract_parts)}"

    def _title_from_html(self, body: str) -> str | None:
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", body, flags=re.IGNORECASE | re.DOTALL)
        if h1_match:
            title = re.sub(r"<[^>]+>", " ", h1_match.group(1))
            normalized = " ".join(title.split()).strip()
            if normalized:
                return normalized
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        if title_match:
            normalized = " ".join(title_match.group(1).split()).strip()
            if normalized and not normalized.lower().startswith("input-"):
                return normalized
        return None
