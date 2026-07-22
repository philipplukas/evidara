"""LexFind API provider — cantonal legislation for 26 cantons + Bund (#731).

LexFind (`www.lexfind.ch`, a project of the *Schweizerische
Staatsschreiberkonferenz*) exposes an unauthenticated JSON API over the same
texts of law the cantons publish themselves. It exists here because the obvious
design — scraping each canton's own portal — **cannot work** for Zürich, and #716
measured why: the ZH-Lex `erlass-*.html` page is metadata-only (`§ = 0` on all 18
sampled pages, 1879→2026), its only text link points at `www.notes.zh.ch` which
refuses TCP on 443 and 80, and the canton's own search API returns 503/204 for
every filter parameter.

One provider covers the cantonal rung for all 28 entities, which is the point:
#628 measures *the cost of the Nth source*, and 28 jurisdictions behind one
homogeneous contract is the cheapest available test of whether that cost falls.

PROVENANCE IS PROVABLE, NOT ASSERTED
------------------------------------
LexFind is a mirror, and a mirror needs justifying. #716 verified the mirrored
file is byte-identical to the canton's own:

    461c614535cb7b5aa33175904f7d3229  Wayback copy of the official notes.zh.ch file
    461c614535cb7b5aa33175904f7d3229  LexFind /tol/22871/de, fetched live

Every record also carries `original_url` back to the canton's own page, so the
canonical citation survives the mirror.

WHAT IS VERIFIED AND WHAT IS NOT
--------------------------------
This module is deliberately explicit about which half of its contract has been
exercised against the live service, because #731 gates live discovery on a
question we have not yet asked the Staatsschreiberkonferenz (their terms and
rate expectations — it is a public-sector service, and we ask rather than find
out by crawling).

  VERIFIED (#716, reproduced end-to-end in curl, no browser, no auth):
    GET /tol/{tol_id}/{lang}                    -> 200 application/pdf
    GET /api/frontend/v1/{lang}/texts-of-law/{tol_id}
    GET /api/frontend/v1/{lang}/entities/extended
    GET /api/frontend/v1/{lang}/categories

  INFERRED — the request body is NOT verified:
    POST /api/frontend/v1/{lang}/fulltext-search

#716 records only that an empty body returns 400 listing 11 required fields; it
does not record their names. :data:`_SEARCH_PAYLOAD_TEMPLATE` is therefore this
module's best reading of the contract and is expected to need correction on
first live contact. It is isolated in one place, and
:meth:`LexFindApiProvider.plan` reports it as unverified so an operator sees that
before dispatching rather than after.

TWO GATES, BOTH APPLIED
-----------------------
Captures are PDFs, so both acquisition gates matter and neither is redundant:

  * :func:`acquisition_core.artifact_guard.check_capture` — the bytes really are
    a PDF. #716 found `OpenAttachment?…` returning a 142-byte JavaScript redirect
    stub under `200`; a provider trusting the status code captures that and
    reports success.
  * :func:`acquisition_core.content_gate.assess_legal_text_density` — abstains on
    `application/pdf` by design (its assessable set is HTML/XML). It is called
    anyway, and its abstention recorded, so the gap is visible in the evidence
    rather than implied by silence. Judging PDF *text* needs extraction, which
    lives in document-intelligence (ADR-0041); see ADR-0047.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from acquisition_core.artifact_guard import check_capture
from acquisition_core.content_gate import assess_legal_text_density
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

_BASE_URL = "https://www.lexfind.ch"
_API_PREFIX = "/api/frontend/v1"
_USER_AGENT = "evidara-lexfind/1.0 (+https://evidara.ai)"

_DEFAULT_LANGUAGE = "de"
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGES = 40

# A cantonal act as PDF. The smallest real one measured in #716 was 84 740 bytes
# (Hundegesetz, 33 pages); the floor is set far below that so a short ordinance is
# not refused, while a 142-byte stub cannot pass.
_DEFAULT_MIN_PDF_BYTES = 2_000

# Temporal validity (#731, and the #661 trap it avoids).
#
# LexFind models repeal SEPARATELY from consolidation date. That is the whole
# reason this source is preferable for temporal questions: Fedlex was measured
# (#661) to leave `dateEndApplicability` open on the newest consolidation of works
# whose `inForceStatus` is "No longer in force", so consolidation dates alone
# report repealed law as currently in force. Here `version_inactive_since` is its
# own field and cannot be masqueraded by an open-ended newest version.
_LEXFIND_IN_FORCE_FROM_FIELD = "version_active_since"
_LEXFIND_IN_FORCE_UNTIL_FIELD = "version_inactive_since"

# UNVERIFIED (see module docstring). #716 established that an empty body returns
# 400 naming 11 required fields but did not record the names. Isolated here so a
# single correction fixes the provider once the live contract is confirmed.
_SEARCH_PAYLOAD_TEMPLATE: dict[str, Any] = {
    "query": "",
    "entity_filter": [],
    "category_filter": [],
    "in_force_only": True,
    "page_no": 1,
    "results_per_page": _DEFAULT_PAGE_SIZE,
}
_SEARCH_PAYLOAD_VERIFIED = False


def _iso_date_or_none(value: Any) -> str | None:
    """Normalise a LexFind date to ISO-8601, or drop it.

    A key that is absent means "unknown", and must stay absent rather than
    becoming a fabricated boundary — the in-force model is four-valued precisely
    so it can answer `unknown` (ADR-0033).
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    return text[:10] if len(text) >= 10 else None


def temporal_metadata(record: dict[str, Any]) -> dict[str, str]:
    """Map a LexFind law record onto the shared temporal-validity keys.

    Emits the exact keys the bundle extraction hints look for, so the window
    reaches `document.metadata.in_force_from` / `.in_force_until` — the paths the
    search projection already coalesces (same contract as `ris_ogd_provider`).

    `is_active: False` with no `version_inactive_since` is recorded as
    `amendment_relation: repealed_by` WITHOUT inventing an end date: we know it
    is no longer in force, and we do not know when it stopped. Those are
    different facts and collapsing them is the #661 failure in the other
    direction.
    """
    out: dict[str, str] = {}
    since = _iso_date_or_none(record.get(_LEXFIND_IN_FORCE_FROM_FIELD))
    until = _iso_date_or_none(record.get(_LEXFIND_IN_FORCE_UNTIL_FIELD))
    if since:
        out["in_force_from"] = since
    if until:
        out["in_force_until"] = until

    is_active = record.get("is_active")
    if is_active is False:
        out["amendment_relation"] = "repealed_by"
    return out


def is_in_force(record: dict[str, Any], *, as_of: str | None = None) -> bool | None:
    """Three-valued in-force answer for a LexFind record, or None when unknown.

    Exists so the repealed-law trap is asserted directly rather than inferred
    from dates downstream: a record with `is_active: False` is NOT in force even
    if its `version_inactive_since` is missing and its `version_active_since` is
    in the past.
    """
    if record.get("is_active") is False:
        return False
    since = _iso_date_or_none(record.get(_LEXFIND_IN_FORCE_FROM_FIELD))
    until = _iso_date_or_none(record.get(_LEXFIND_IN_FORCE_UNTIL_FIELD))
    if since is None:
        return None
    moment = as_of or datetime.now(UTC).date().isoformat()
    if moment < since:
        return False
    if until is not None and moment >= until:
        return False
    return True


class LexFindApiProvider:
    """Acquisition provider for LexFind's texts-of-law API."""

    provider_name = "lexfind_api"
    # start_run is implemented and unit-tested against fixtures, and the capture
    # path is verified live (#716). No operator has captured an ADR-0030
    # acceptance run yet, and the discovery payload is unverified, so the code key
    # admits an ACCEPTANCE run and nothing else.
    readiness = AcquisitionReadiness.AWAITING_EVIDENCE

    def plan(self, source: Source, source_version: SourceVersion) -> ProviderPlan:
        spec = source_version.acquisition_spec or {}
        language = spec.get("language") or _DEFAULT_LANGUAGE
        entity_ids = list(spec.get("entity_ids") or [])
        page_size = int(spec.get("results_per_page") or _DEFAULT_PAGE_SIZE)
        max_pages = int(spec.get("max_pages") or _MAX_PAGES)

        notes = [
            "Capture path verified live (#716): /tol/{id}/{lang} returns "
            "application/pdf, md5-identical to the canton's own file.",
        ]
        if not _SEARCH_PAYLOAD_VERIFIED:
            notes.append(
                "DISCOVERY UNVERIFIED: the POST /fulltext-search request body is "
                "this provider's reading of the contract, not a measured one. "
                "Expect the first live run to correct it (#731)."
            )
        if not entity_ids:
            notes.append(
                "No entity_ids in the acquisition spec — discovery would span every "
                "entity. Set entity_ids (ZH = 26) to scope the run."
            )

        return ProviderPlan(
            provider=self.provider_name,
            mode=spec.get("mode"),
            seed_urls=[f"{_BASE_URL}{_API_PREFIX}/{language}/fulltext-search"],
            estimated_request_count=max_pages + page_size,
            max_discovery_depth=0,
            user_agent=_USER_AGENT,
            request_timeout_seconds=float(spec.get("request_timeout_seconds") or 20.0),
            notes=notes,
            raw={
                "entity_ids": entity_ids,
                "language": language,
                "results_per_page": page_size,
                "search_payload_verified": _SEARCH_PAYLOAD_VERIFIED,
            },
        )

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        spec = source_version.acquisition_spec or {}
        language = spec.get("language") or _DEFAULT_LANGUAGE
        entity_ids = list(spec.get("entity_ids") or [])
        category_ids = list(spec.get("category_ids") or [])
        page_size = int(spec.get("results_per_page") or _DEFAULT_PAGE_SIZE)
        max_pages = int(spec.get("max_pages") or _MAX_PAGES)
        max_documents = int(spec.get("max_documents") or 0)
        min_pdf_bytes = int(spec.get("min_pdf_bytes") or _DEFAULT_MIN_PDF_BYTES)
        timeout_seconds = float(spec.get("request_timeout_seconds") or 20.0)

        resources: list[ProviderResource] = []
        skipped: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []

        async with httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            try:
                tol_ids = await self._discover(
                    client,
                    language=language,
                    entity_ids=entity_ids,
                    category_ids=category_ids,
                    page_size=page_size,
                    max_pages=max_pages,
                )
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                failures.append(
                    {
                        "url": f"{_API_PREFIX}/{language}/fulltext-search",
                        "error": str(exc),
                    }
                )
                tol_ids = []

            if max_documents:
                tol_ids = tol_ids[:max_documents]

            for tol_id in tol_ids:
                try:
                    resource = await self._capture(
                        client,
                        tol_id=tol_id,
                        language=language,
                        run=run,
                        min_pdf_bytes=min_pdf_bytes,
                        skipped=skipped,
                    )
                except Exception as exc:  # noqa: BLE001
                    failures.append({"url": f"/tol/{tol_id}/{language}", "error": str(exc)})
                    continue
                if resource is not None:
                    resources.append(resource)

        return ProviderStartResult(
            external_job_id=f"lexfind-{run.run_id}",
            provider=self.provider_name,
            request_payload={
                "language": language,
                "entity_ids": entity_ids,
                "category_ids": category_ids,
                "search_payload_verified": _SEARCH_PAYLOAD_VERIFIED,
            },
            response_payload={
                "captured": len(resources),
                "skipped": skipped,
                "failures": failures,
            },
            inline_resources=resources,
            inline_failure_reason=failures[0]["error"] if failures and not resources else None,
        )

    async def _discover(
        self,
        client: httpx.AsyncClient,
        *,
        language: str,
        entity_ids: list[int],
        category_ids: list[int],
        page_size: int,
        max_pages: int,
    ) -> list[int]:
        """Return tol ids for the requested entities.

        Two calls per page by the API's design: a POST that opens a search
        session, then a GET that pages through it.
        """
        payload = dict(_SEARCH_PAYLOAD_TEMPLATE)
        payload["entity_filter"] = entity_ids
        payload["category_filter"] = category_ids
        payload["results_per_page"] = page_size

        opened = await client.post(f"{_API_PREFIX}/{language}/fulltext-search", json=payload)
        opened.raise_for_status()
        session = opened.json()
        search_id = session.get("id")
        session_id = session.get("session_id")
        if search_id is None:
            return []

        tol_ids: list[int] = []
        seen: set[int] = set()
        for page_no in range(1, max_pages + 1):
            page = await client.get(
                f"{_API_PREFIX}/{language}/fulltext-search/{search_id}",
                params={
                    "session_id": session_id,
                    "page_no": page_no,
                    "results_per_page": page_size,
                },
            )
            page.raise_for_status()
            rows = page.json().get("results") or []
            if not rows:
                break
            for row in rows:
                tol_id = row.get("text_of_law_id") or row.get("tol_id") or row.get("id")
                if isinstance(tol_id, int) and tol_id not in seen:
                    seen.add(tol_id)
                    tol_ids.append(tol_id)
        return tol_ids

    async def _capture(
        self,
        client: httpx.AsyncClient,
        *,
        tol_id: int,
        language: str,
        run: Run,
        min_pdf_bytes: int,
        skipped: list[dict[str, Any]],
    ) -> ProviderResource | None:
        """Fetch one text of law as PDF, guarded, with its temporal window."""
        record_response = await client.get(f"{_API_PREFIX}/{language}/texts-of-law/{tol_id}")
        record_response.raise_for_status()
        record = record_response.json() or {}

        pdf_url = f"/tol/{tol_id}/{language}"
        pdf = await client.get(pdf_url)
        pdf.raise_for_status()
        body = pdf.content
        declared = pdf.headers.get("content-type")

        verdict = check_capture(
            body=body,
            expected_content_type="application/pdf",
            declared_content_type=declared,
            min_bytes=min_pdf_bytes,
        )
        if not verdict:
            # Recorded, never guessed at: an operator reading the evidence must be
            # able to tell a stub from an empty source (#716, ADR-0047).
            skipped.append(
                {
                    "tol_id": tol_id,
                    "url": pdf_url,
                    "reason": verdict.reason,
                    "detail": verdict.detail,
                }
            )
            return None

        # Abstains on application/pdf by design; called so the abstention is in the
        # evidence rather than implied by its absence. See ADR-0047.
        assessment = assess_legal_text_density("", content_type="application/pdf")

        metadata: dict[str, Any] = {
            "provider": self.provider_name,
            "tol_id": tol_id,
            "language": language,
            "run_id": run.run_id,
            "fetched_at": datetime.now(UTC).isoformat(),
            "capture_guard": "passed",
            "legal_text_assessment": "abstained_binary_manifestation",
            "legal_text_evidence": assessment.as_evidence(),
        }
        # `original_url` is what keeps the canonical citation pointing at the
        # canton rather than at the mirror.
        if record.get("original_url"):
            metadata["original_url"] = record["original_url"]
        if record.get("entity_id") is not None:
            metadata["lexfind_entity_id"] = record["entity_id"]
        metadata.update(temporal_metadata(record))

        in_force = is_in_force(record)
        if in_force is not None:
            metadata["in_force"] = in_force

        return ProviderResource(
            source_url=record.get("original_url") or f"{_BASE_URL}{pdf_url}",
            final_url=f"{_BASE_URL}{pdf_url}",
            content_type="application/pdf",
            body_bytes=body,
            title=record.get("title") or record.get("short_title"),
            http_status=pdf.status_code,
            discovery_depth=0,
            metadata=metadata,
        )
