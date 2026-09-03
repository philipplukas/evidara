"""OGD-RIS API provider for Austrian legal documents.

Uses the official Open Government Data REST API provided by the Austrian
Federal Chancellery (Bundeskanzleramt) at https://data.bka.gv.at/ris/api/v2.6/
to discover and fetch federal legislation and court decisions.
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
from platform_control.services.politeness import limited_get

logger = logging.getLogger(__name__)

_BASE_URL = "https://data.bka.gv.at/ris/api/v2.6"
_USER_AGENT = "evidara-ris-ogd/1.0 (+https://evidara.ai)"

_APPLIKATION_TO_DOCTYPE: dict[str, str] = {
    "BrKons": "law",
    "BgblAuth": "law",
    "BgblPdf": "law",
    "Erv": "law",
    "Vfgh": "decision",
    "Vwgh": "decision",
    "Bvwg": "decision",
    "Justiz": "decision",
}

_FORMAT_PREFERENCE = ("Xml", "Html")
_FORMAT_CONTENT_TYPE: dict[str, str] = {
    "Xml": "application/xml",
    "Html": "text/html",
    "Pdf": "application/pdf",
    "Rtf": "application/rtf",
}

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGES = 50

# Temporal validity (#663). VERIFIED against the live OGD API (2026-07-19): every
# `BrKons` document reference carries `Bundesrecht.BrKons.Inkrafttretensdatum`
# (540/540 sampled) and, when the norm has ceased to apply,
# `Ausserkrafttretensdatum`. Both are already ISO-8601 in the JSON listing — the
# per-document RIS XML publishes the same two values as `ct="ikra"` / `ct="akra"`
# in DD.MM.YYYY, which is why acquisition is the better place to read them.
_RIS_IN_FORCE_FROM_FIELD = "Inkrafttretensdatum"
_RIS_IN_FORCE_UNTIL_FIELD = "Ausserkrafttretensdatum"

# Act-level relation signal, the closest RIS analogue to Fedlex `jolux:inForceStatus`
# (#661). `NovellenBeziehung` states how this norm relates to the amending act
# (Novelle). Observed live across 540 sampled norms, only these two values occur,
# plus absence:
#   "aufgehoben durch"       → repealed by
#   "zuletzt geändert durch" → last amended by
#
# Unlike Fedlex, this signal does NOT need to override the window. Measured live
# (#663): of 27 acts sampled, 11 carry a repeal signal, and **0** of them have an
# open-ended newest version — RIS closes `Ausserkrafttretensdatum` on every
# version of a repealed act (checked per act: 4, 8, 32, 22, 16, 22, 4 and 22
# versions, all closed). The Fedlex trap — a repealed work whose newest
# consolidation is open-ended, so version dates alone report repealed law as
# current — therefore does not reproduce in RIS. We record the signal as
# corroboration rather than as an override; see the module docs for why.
_RIS_AMENDMENT_RELATION_FIELD = "NovellenBeziehung"
_AMENDMENT_RELATION_BY_RIS_VALUE = {
    "aufgehoben durch": "repealed_by",
    "zuletzt geändert durch": "last_amended_by",
}


def _iso_date_or_none(value: Any) -> str | None:
    """Return `value` as an ISO-8601 date string, or None if it is not one.

    RIS publishes these fields as ISO in the OGD JSON, but a value we cannot
    parse is reported as None rather than guessed at: the downstream in-force
    model is four-valued precisely so it can answer `unknown`, and a wrong date
    is worse than a missing one.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _format_date(value: Any) -> str:
    """Convert ISO date/datetime string to DD.MM.YYYY for the OGD API."""
    s = str(value)
    if "T" in s:
        s = s.split("T")[0]
    parts = s.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return s


class RisOgdProvider:
    """Acquisition provider that pages through the OGD-RIS REST API."""

    provider_name = "ris_ogd"
    readiness = AcquisitionReadiness.LIVE

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        acquisition_spec = source_version.acquisition_spec or {}
        base_url = str(acquisition_spec.get("base_url") or f"{_BASE_URL}/Bundesrecht")
        applikation = acquisition_spec.get("applikation")
        preferred_formats = acquisition_spec.get("preferred_formats") or list(_FORMAT_PREFERENCE)
        page_size = int(acquisition_spec.get("page_size") or _DEFAULT_PAGE_SIZE)
        max_pages = int(acquisition_spec.get("max_pages") or _MAX_PAGES)
        max_content_bytes = int(acquisition_spec.get("max_content_bytes") or 5_000_000)
        request_timeout_seconds = float(acquisition_spec.get("request_timeout_seconds") or 15.0)

        run_scope = run.scope or {}
        since_date = run_scope.get("since")
        until_date = run_scope.get("until")

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []
        seen_ris_ids: set[str] = set()
        skipped_duplicates = 0

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                timeout=request_timeout_seconds,
                connect=min(10.0, request_timeout_seconds),
            ),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            for page_number in range(1, max_pages + 1):
                params: dict[str, Any] = {
                    "Seitennummer": page_number,
                    "Seitengroesse": page_size,
                }
                if applikation:
                    params["Applikation"] = applikation
                if since_date:
                    params["ImRisSeitDatumVon"] = _format_date(since_date)
                if until_date:
                    params["ImRisSeitDatumBis"] = _format_date(until_date)

                try:
                    listing = await limited_get(client, base_url, params=params)
                    listing.raise_for_status()
                    listing_json = listing.json()
                except httpx.TimeoutException:
                    failures.append(
                        {
                            "url": base_url,
                            "error": (
                                "listing page "
                                f"{page_number}: timed out after {request_timeout_seconds:.1f}s"
                            ),
                        }
                    )
                    break
                except Exception as exc:
                    failures.append(
                        {
                            "url": base_url,
                            "error": f"listing page {page_number}: {exc}",
                        }
                    )
                    break

                api_error = (listing_json.get("OgdSearchResult") or {}).get("Error")
                if api_error:
                    failures.append(
                        {
                            "url": base_url,
                            "error": f"OGD API error: {api_error.get('Message', str(api_error))}",
                        }
                    )
                    break

                refs = _extract_document_refs(listing_json)
                if not refs:
                    break

                for ref in refs:
                    ris_id = _extract_metadata(ref).get("ris_id", "")
                    if ris_id and ris_id in seen_ris_ids:
                        skipped_duplicates += 1
                        continue
                    if ris_id:
                        seen_ris_ids.add(ris_id)

                    doc_result = await _fetch_single_document(
                        client=client,
                        ref=ref,
                        preferred_formats=preferred_formats,
                        max_content_bytes=max_content_bytes,
                        request_timeout_seconds=request_timeout_seconds,
                        run=run,
                    )
                    if isinstance(doc_result, ProviderResource):
                        resources.append(doc_result)
                    else:
                        failures.append(doc_result)

                total_hits = _total_hits(listing_json)
                if total_hits is not None and page_number * page_size >= total_hits:
                    break

        response_payload = {
            "provider": self.provider_name,
            "base_url": base_url,
            "applikation": applikation,
            "since": since_date,
            "until": until_date,
            "captured": len(resources),
            "failed": len(failures),
            "skipped_duplicates": skipped_duplicates,
            "failures": failures[:20],
        }
        inline_failure_reason = None
        if not resources:
            inline_failure_reason = (
                f"RIS OGD provider did not capture any resources (failures={len(failures)})."
            )

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"ris_ogd_{run.run_id}",
            request_payload={
                "base_url": base_url,
                "applikation": applikation,
                "page_size": page_size,
                "max_pages": max_pages,
            },
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
        base_url = str(acquisition_spec.get("base_url") or f"{_BASE_URL}/Bundesrecht")
        page_size = int(acquisition_spec.get("page_size") or _DEFAULT_PAGE_SIZE)
        max_pages = int(acquisition_spec.get("max_pages") or _MAX_PAGES)
        notes: list[str] = []
        if applikation := acquisition_spec.get("applikation"):
            notes.append(f"applikation={applikation}")
        return ProviderPlan(
            provider=self.provider_name,
            mode="ogd_rest_paged",
            seed_urls=[base_url],
            estimated_request_count=page_size * max_pages,
            user_agent=str(acquisition_spec.get("user_agent") or _USER_AGENT),
            request_timeout_seconds=float(acquisition_spec.get("request_timeout_seconds") or 15.0),
            notes=notes,
            raw=dict(acquisition_spec),
        )


def _extract_document_refs(listing_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull individual document references out of the OGD search result."""
    search_result = listing_json.get("OgdSearchResult") or {}
    doc_results = search_result.get("OgdDocumentResults") or {}
    refs_raw = doc_results.get("OgdDocumentReference")
    if refs_raw is None:
        return []
    if isinstance(refs_raw, dict):
        refs_raw = [refs_raw]
    return [r for r in refs_raw if isinstance(r, dict)]


def _total_hits(listing_json: dict[str, Any]) -> int | None:
    try:
        hits_block = (
            listing_json.get("OgdSearchResult", {}).get("OgdDocumentResults", {}).get("Hits", {})
        )
        if isinstance(hits_block, dict):
            return int(hits_block.get("#text", 0))
        return int(hits_block)
    except (TypeError, ValueError):
        return None


def _select_content_url(
    ref: dict[str, Any],
    preferred_formats: list[str],
) -> tuple[str, str] | None:
    """Pick best download URL from a document reference, returns (url, data_type)."""
    data = ref.get("Data") or {}
    doc_list = data.get("Dokumentliste") or {}
    content_refs = doc_list.get("ContentReference")
    if content_refs is None:
        return None
    if isinstance(content_refs, dict):
        content_refs = [content_refs]

    main_docs = [cr for cr in content_refs if cr.get("ContentType") == "MainDocument"]
    if not main_docs:
        main_docs = content_refs

    for fmt in preferred_formats:
        for cr in main_docs:
            urls_block = (cr.get("Urls") or {}).get("ContentUrl")
            if urls_block is None:
                continue
            if isinstance(urls_block, dict):
                urls_block = [urls_block]
            for url_entry in urls_block:
                if url_entry.get("DataType") == fmt and url_entry.get("Url"):
                    return (url_entry["Url"], fmt)
    return None


def _extract_metadata(ref: dict[str, Any]) -> dict[str, Any]:
    data = ref.get("Data") or {}
    meta = data.get("Metadaten") or {}
    tech = meta.get("Technisch") or {}
    allgemein = meta.get("Allgemein") or {}

    bundesrecht = meta.get("Bundesrecht") or {}
    judikatur = meta.get("Judikatur") or {}
    domain_meta = bundesrecht or judikatur

    applikation = tech.get("Applikation", "")
    document_type = _APPLIKATION_TO_DOCTYPE.get(applikation, "")

    # Temporal validity (#663) lives one level further down, in the
    # application-specific block (`BrKons` for consolidated federal law).
    domain_detail = domain_meta.get(applikation) if isinstance(domain_meta, dict) else None
    if not isinstance(domain_detail, dict):
        domain_detail = {}

    return {
        "ris_id": tech.get("ID", ""),
        "applikation": applikation,
        "document_type": document_type,
        "organ": tech.get("Organ", ""),
        "document_url": allgemein.get("DokumentUrl", ""),
        "title": domain_meta.get("Titel", ""),
        "short_title": domain_meta.get("Kurztitel", ""),
        "eli": domain_meta.get("Eli", ""),
        # Omitted (None), never defaulted, when RIS does not publish them: an
        # absent `Ausserkrafttretensdatum` means the norm is still in force, and
        # an unparseable value must stay `unknown` rather than become a guess.
        "in_force_from": _iso_date_or_none(domain_detail.get(_RIS_IN_FORCE_FROM_FIELD)),
        "in_force_until": _iso_date_or_none(domain_detail.get(_RIS_IN_FORCE_UNTIL_FIELD)),
        "amendment_relation": _amendment_relation(domain_detail),
        "gesetzesnummer": domain_detail.get("Gesetzesnummer") or "",
    }


def _amendment_relation(domain_detail: dict[str, Any]) -> str | None:
    """Map RIS `NovellenBeziehung` onto our controlled vocabulary.

    Returns `repealed_by` / `last_amended_by`, or None when RIS publishes no
    relation *or* publishes a value we do not recognise. An unrecognised value is
    reported as None rather than mapped onto a plausible guess — the same rule
    #661 applies to unknown Fedlex enforcement-status codes.
    """
    raw = domain_detail.get(_RIS_AMENDMENT_RELATION_FIELD)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return _AMENDMENT_RELATION_BY_RIS_VALUE.get(raw.strip().lower())


async def _fetch_single_document(
    *,
    client: httpx.AsyncClient,
    ref: dict[str, Any],
    preferred_formats: list[str],
    max_content_bytes: int,
    request_timeout_seconds: float,
    run: Run,
) -> ProviderResource | dict[str, str]:
    """Fetch a single document. Returns ProviderResource on success, failure dict otherwise."""
    meta = _extract_metadata(ref)
    ris_id = meta.get("ris_id") or "unknown"

    selected = _select_content_url(ref, preferred_formats)
    if selected is None:
        return {"url": meta.get("document_url", ris_id), "error": "no downloadable content URL"}

    url, data_type = selected
    content_type = _FORMAT_CONTENT_TYPE.get(data_type, "application/octet-stream")

    try:
        response = await limited_get(client, url)
        response.raise_for_status()
    except httpx.TimeoutException:
        return {"url": url, "error": f"timed out after {request_timeout_seconds:.1f}s"}
    except Exception as exc:
        return {"url": url, "error": str(exc)}

    body_bytes = response.content
    if len(body_bytes) > max_content_bytes:
        return {"url": url, "error": f"content exceeds {max_content_bytes} bytes"}

    # `content_type` is the RIS *listing's* promise (`Data.…DataType` -> Xml/Html/
    # Pdf), made before the download URL was fetched, so `check_capture` is what
    # holds the OGD endpoint to it. Note what this catches that nothing else does:
    # this function decodes every body as text, so an `Rtf`/`Pdf` download that
    # arrived where `Xml` was promised would be UTF-8-mangled and captured as a
    # document. `_FORMAT_PREFERENCE` defaults to Xml/Html, but `preferred_formats`
    # is operator-settable, so that path is reachable by configuration alone.
    verdict = check_capture(
        body=body_bytes,
        expected_content_type=content_type,
        declared_content_type=response.headers.get("content-type"),
    )
    if not verdict:
        return {"url": url, "error": f"{verdict.reason}: {verdict.detail}"}

    charset = response.charset_encoding or "utf-8"
    body = body_bytes.decode(charset, errors="replace")
    actual_ct = response.headers.get("content-type", content_type)
    normalized_ct = actual_ct.split(";")[0].strip().lower()

    # Legal-text density (#631). RIS Bundesrecht is German and cites `§` and `Abs.`
    # throughout, so the shared DE/IT vocabulary fits this source directly. The gate
    # abstains on any content type it cannot read, so a format outside HTML/XML
    # passes through untouched rather than being guessed at.
    assessment = assess_legal_text_density(body, content_type=normalized_ct)
    if not assessment.is_legal_text:
        return {"url": url, "error": f"no_legal_text_markers: {assessment.reason}"}

    resource_metadata: dict[str, Any] = {
        "provider": "ris_ogd",
        "ris_id": ris_id,
        "applikation": meta.get("applikation"),
        "document_type": meta.get("document_type"),
        "eli": meta.get("eli"),
        "short_title": meta.get("short_title"),
        "organ": meta.get("organ"),
        "data_type": data_type,
        "fetched_at": datetime.now(UTC).isoformat(),
        "run_id": run.run_id,
    }

    # Temporal validity (#663). These land on the resource metadata under the
    # exact keys `build_bundle_extraction_hints` looks for, so the window reaches
    # `document.metadata.in_force_from` / `.in_force_until` — the paths the search
    # projection already coalesces. Keys stay ABSENT when RIS did not publish
    # them; the in-force model is four-valued so it can answer `unknown`, and
    # handing it a fabricated date is what ADR-0033 exists to prevent.
    for key in ("in_force_from", "in_force_until", "amendment_relation"):
        value = meta.get(key)
        if value:
            resource_metadata[key] = value
    if meta.get("gesetzesnummer"):
        resource_metadata["gesetzesnummer"] = meta["gesetzesnummer"]
    resource_metadata["capture_guard"] = "passed"
    resource_metadata["legal_text_evidence"] = assessment.as_evidence()

    return ProviderResource(
        source_url=meta.get("document_url") or url,
        final_url=url,
        content_type=normalized_ct,
        body=body,
        title=meta.get("title") or meta.get("short_title"),
        http_status=response.status_code,
        discovery_depth=0,
        metadata=resource_metadata,
    )
