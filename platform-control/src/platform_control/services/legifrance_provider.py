"""Legifrance (PISTE/DILA) API provider for French legal documents.

Uses the PISTE/DILA API at https://api.piste.gouv.fr/dila/legifrance/lf-engine-app
to discover and fetch French legislation via OAuth 2.0 client credentials.

Registration: https://piste.gouv.fr/registration

Prerequisite: OAuth client_id/client_secret must be configured as
PLATFORM_CONTROL_LEGIFRANCE_CLIENT_ID / PLATFORM_CONTROL_LEGIFRANCE_CLIENT_SECRET
in the platform-control settings. Until then the provider remains a scaffold
(live_ready=False) and blueprint templates referencing it parse but reject runs.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    AcquisitionReadiness,
    ProviderPlan,
    ProviderResource,
    ProviderStartResult,
)

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
_API_BASE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
_USER_AGENT = "evidara-legifrance/1.0 (+https://evidara.ai)"

_DEFAULT_MAX_ARTICLES = 100
_DEFAULT_PAGE_SIZE = 25

# LEGITEXT IDs for core French codes
_SEED_CODES: list[dict[str, str]] = [
    {"id": "LEGITEXT000006070721", "title": "Code civil"},
    {"id": "LEGITEXT000006070719", "title": "Code pénal"},
    {"id": "LEGITEXT000006070933", "title": "Code de commerce"},
    {"id": "LEGITEXT000006072050", "title": "Code du travail"},
    {"id": "LEGITEXT000006069577", "title": "Code général des impôts"},
    {"id": "LEGITEXT000006074228", "title": "Code de procédure pénale"},
    {"id": "LEGITEXT000006070716", "title": "Code de procédure civile"},
    {"id": "LEGITEXT000006072665", "title": "Code de la santé publique"},
    {"id": "LEGITEXT000006074075", "title": "Code de l'urbanisme"},
    {"id": "LEGITEXT000006070633", "title": "Code de la consommation"},
]


class LegifranceProvider:
    """Scaffold provider for French law via the PISTE/DILA Legifrance API.

    This provider is NOT live-ready until PISTE API credentials are configured.
    Set live_ready = True once credentials are available and tested.
    """

    provider_name = "legifrance"
    readiness = AcquisitionReadiness.SCAFFOLD

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        """Obtain an OAuth 2.0 access token via client_credentials grant."""
        if not self._client_id or not self._client_secret:
            raise RuntimeError(
                "Legifrance provider requires PLATFORM_CONTROL_LEGIFRANCE_CLIENT_ID "
                "and PLATFORM_CONTROL_LEGIFRANCE_CLIENT_SECRET"
            )
        response = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "openid",
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        acquisition_spec = source_version.acquisition_spec or {}
        code_ids = acquisition_spec.get("code_ids") or [c["id"] for c in _SEED_CODES]
        max_articles = int(acquisition_spec.get("max_articles") or _DEFAULT_MAX_ARTICLES)

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            access_token = await self._get_access_token(client)
            auth_headers = {"Authorization": f"Bearer {access_token}"}

            for code_entry in code_ids:
                code_id = code_entry if isinstance(code_entry, str) else code_entry.get("id", "")
                if not code_id:
                    continue

                try:
                    toc_response = await client.post(
                        f"{_API_BASE}/consult/code/tableMatieres",
                        headers=auth_headers,
                        json={"textId": code_id, "date": datetime.now(UTC).strftime("%Y-%m-%d")},
                    )
                    toc_response.raise_for_status()
                    toc_data = toc_response.json()
                except Exception as exc:
                    failures.append({"url": code_id, "error": f"table of contents: {exc}"})
                    continue

                articles = _extract_article_ids(toc_data)[:max_articles]
                code_title = _extract_code_title(toc_data, code_id)

                for article_id in articles:
                    result = await _fetch_article(
                        client=client,
                        auth_headers=auth_headers,
                        article_id=article_id,
                        code_id=code_id,
                        code_title=code_title,
                        run=run,
                    )
                    if isinstance(result, ProviderResource):
                        resources.append(result)
                    else:
                        failures.append(result)

        response_payload = {
            "provider": self.provider_name,
            "code_ids": code_ids,
            "captured": len(resources),
            "failed": len(failures),
            "failures": failures[:20],
        }
        inline_failure_reason = None
        if not resources:
            inline_failure_reason = (
                f"Legifrance provider did not capture any resources (failures={len(failures)})."
            )

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"legifrance_{run.run_id}",
            request_payload={"code_ids": code_ids, "max_articles": max_articles},
            response_payload=response_payload,
            inline_resources=resources,
            inline_failure_reason=inline_failure_reason,
        )

    def plan(
        self,
        source: Source,
        source_version: SourceVersion,
    ) -> ProviderPlan:
        del source
        acquisition_spec = source_version.acquisition_spec or {}
        code_ids = acquisition_spec.get("code_ids") or [c["id"] for c in _SEED_CODES]
        max_articles = int(acquisition_spec.get("max_articles") or _DEFAULT_MAX_ARTICLES)
        return ProviderPlan(
            provider=self.provider_name,
            mode="piste_api_code_articles",
            seed_urls=[f"https://www.legifrance.gouv.fr/codes/texte_lc/{cid}" for cid in code_ids],
            estimated_request_count=len(code_ids) * max_articles,
            user_agent=_USER_AGENT,
            request_timeout_seconds=30.0,
            notes=["OAuth 2.0 via PISTE/DILA", f"{len(code_ids)} codes"],
            raw=dict(acquisition_spec),
        )


def _extract_article_ids(toc_data: dict[str, Any]) -> list[str]:
    """Recursively extract article IDs from the Legifrance table of contents."""
    ids: list[str] = []
    _walk_toc(toc_data, ids)
    return ids


def _walk_toc(node: Any, ids: list[str]) -> None:
    if isinstance(node, dict):
        if article_id := node.get("id"):
            if isinstance(article_id, str) and article_id.startswith("LEGIARTI"):
                ids.append(article_id)
        for value in node.values():
            _walk_toc(value, ids)
    elif isinstance(node, list):
        for item in node:
            _walk_toc(item, ids)


def _extract_code_title(toc_data: dict[str, Any], code_id: str) -> str:
    title = toc_data.get("title") or toc_data.get("titre") or ""
    if not title:
        for seed in _SEED_CODES:
            if seed["id"] == code_id:
                return seed["title"]
    return str(title) or code_id


async def _fetch_article(
    *,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    article_id: str,
    code_id: str,
    code_title: str,
    run: Run,
) -> ProviderResource | dict[str, str]:
    """Fetch a single article from the Legifrance API."""
    try:
        response = await client.post(
            f"{_API_BASE}/consult/getArticle",
            headers=auth_headers,
            json={"id": article_id},
        )
        response.raise_for_status()
        article = response.json()
    except Exception as exc:
        return {"url": article_id, "error": str(exc)}

    text_html = article.get("texteHtml") or article.get("texte") or ""
    title = article.get("num") or article.get("titre") or article_id

    if not text_html:
        return {"url": article_id, "error": "empty article content"}

    legifrance_url = f"https://www.legifrance.gouv.fr/codes/article_lc/{article_id}"

    return ProviderResource(
        source_url=legifrance_url,
        final_url=legifrance_url,
        content_type="text/html",
        body=text_html,
        title=f"{code_title} - {title}",
        http_status=200,
        discovery_depth=0,
        metadata={
            "provider": "legifrance",
            "article_id": article_id,
            "code_id": code_id,
            "code_title": code_title,
            "fetched_at": datetime.now(UTC).isoformat(),
            "run_id": run.run_id,
        },
    )
