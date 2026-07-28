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

THE CONTRACT, VERIFIED LIVE 2026-07-22
--------------------------------------
`robots.txt` declares no rules at all — nothing is disallowed. Requests were made
one at a time with several seconds between them and an identifying User-Agent.

    POST /api/frontend/v1/{lang}/fulltext-search   -> {id, session_id, search}
    GET  /api/frontend/v1/{lang}/fulltext-search/{id}?session_id=&page_no=&results_per_page=
    GET  /tol/{tol_id}/{lang}                      -> 200 application/pdf

Four findings, each of which the first draft of this module got wrong:

  1. **All eleven POST fields are required** and none is named what the issue
     text implied. See :data:`_SEARCH_PAYLOAD_TEMPLATE`.
  2. **`search_text` must be non-empty.** `""` returns 400. There is no
     "list everything for this entity" call — see `_discover` for what replaces it.
  3. **Results are under `texts_of_law_with_matches`.** `results` is a
     per-language *count* array; reading it as the hit list yields four rows of
     nothing.
  4. **Dates are `DD.MM.YYYY`**, not ISO. See :func:`_iso_date_or_none` for why
     passing them through unconverted is a live data-corruption defect.

Temporal fields live on the **version** record inside `matches[]`, and the
canton's `original_url` on the **download** entry inside `dta_urls[]` — neither
is at the record root.

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
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from acquisition_core.artifact_guard import check_capture
from acquisition_core.content_gate import assess_legal_text_density
from platform_control.domain import DenominatorTier
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

# LexFind publishes Swiss-format dates (`01.06.2025`), not ISO. See
# `_iso_date_or_none` for why passing them through unconverted is a live defect.
_SWISS_DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# VERIFIED against the live endpoint 2026-07-22. All eleven fields are required:
# an empty body returns 400 naming every one of them.
#
# `search_text` must be NON-EMPTY -- `""` returns 400 "Ungültige Anfrage". There
# is therefore no "list everything for this entity" call, which is the single
# most consequential fact about this API's discovery model. See `_discover`.
_SEARCH_PAYLOAD_TEMPLATE: dict[str, Any] = {
    "search_text": "",
    "active_only": True,
    "search_in_systematic_number": True,
    "search_in_title": True,
    "search_in_keywords": True,
    "search_in_content": False,
    "entity_filter": [],
    "systematic_filter": [],
    "category_filter": [],
    "use_global_systematics": False,
    "direct_search": False,
}
_SEARCH_PAYLOAD_VERIFIED = True

# ---------------------------------------------------------------------------
# Enumeration (#816) — how to hold a whole corpus rather than a branch
# ---------------------------------------------------------------------------
#
# The search endpoint has no list-everything call, but that constrains the QUERY,
# not the corpus. Matching on `search_in_systematic_number` is **contains**, and
# every systematic number contains at least one digit, so the UNION over digits
# 0-9 is the entire entity by construction. Dedup by `tol id` collapses it.
#
# The sum is meaningless and the union is exact — measured on ZH 2026-07-28:
#
#     naive sum over digits : 2613   (a systematic number holds ~1.9 distinct digits)
#     deduplicated union    : 1377
#     entities/extended     : 1377   <- published total, exact match
#     requests used         :   40
#
# ~40 requests per entity, so ~1100 for all 28 — against ~35 000 for sweeping the
# `/texts-of-law/{id}` space, which remains the fallback if a canton's numbering
# ever breaks the digit assumption.
#
# This payload differs from _SEARCH_PAYLOAD_TEMPLATE in two ways that the proof
# depends on, so it is declared separately rather than patched at the call site:
#
#   active_only: False          — ZH's 1377 includes 433 REPEALED acts. Enumerating
#                                 with active_only=True reconciles against 944 and
#                                 looks correct while silently dropping a third of
#                                 the corpus. Point-in-time questions need repealed law.
#   title/keywords: False       — the union is proven over systematic numbers alone.
#                                 Leaving these on cannot lose records, but it makes
#                                 the observed count mean something other than what
#                                 was verified against the published denominator.
_ENUMERATION_DIGITS = "0123456789"
_ENUMERATION_STRATEGY_DIGIT_UNION = "systematic_digit_union"
_ENUMERATION_PAYLOAD_TEMPLATE: dict[str, Any] = {
    "search_text": "",
    "active_only": False,
    "search_in_systematic_number": True,
    "search_in_title": False,
    "search_in_keywords": False,
    "search_in_content": False,
    "entity_filter": [],
    "systematic_filter": [],
    "category_filter": [],
    "use_global_systematics": False,
    "direct_search": False,
}
_ENTITIES_PATH = "entities/extended"

# Results live here. `results` is NOT the hit list -- it is a per-language count
# array (`[{language: de, number_of_results: 2}, ...]`), and reading it as hits
# yields four rows of nothing for every query.
_RESULTS_KEY = "texts_of_law_with_matches"


def _iso_date_or_none(value: Any) -> str | None:
    """Normalise a LexFind date to ISO-8601, or drop it.

    **LexFind publishes `DD.MM.YYYY`**, verified live: `"01.06.2025"`,
    `"14.04.2008"`. It is not ISO and must not be passed through as though it
    were — a naive truncation turns 1 June 2025 into "01.06.2025", which any ISO
    reader downstream parses as a different date or not at all. That value would
    land on `document.metadata.in_force_from`, which the search projection
    coalesces, so a wrong date here becomes a wrong in-force answer with no
    visible failure anywhere in between.

    ISO input is accepted too, so a future format change on their side does not
    silently start dropping every date.

    A key that is absent means "unknown", and must stay absent rather than
    becoming a fabricated boundary — the in-force model is multi-valued precisely
    so it can answer `unknown` (ADR-0033).
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if _SWISS_DATE_RE.fullmatch(text):
        day, month, year = text.split(".")
        return f"{year}-{month}-{day}"
    if _ISO_DATE_RE.match(text):
        return text[:10]
    # Unrecognised shape: refuse rather than guess. A mangled date is worse than
    # an absent one, because absence is honest and downstream can say "unknown".
    logger.warning("lexfind: unrecognised date format %r — dropped", text)
    return None


def _positive_int_or_none(value: Any) -> int | None:
    """A denominator, or None — never zero.

    Zero is not a count we can reconcile against: a source reporting no law at all is
    unstatable, and treating it as a denominator makes `observed == 0` read as complete
    coverage. Anything non-numeric is likewise unknown rather than empty.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value) if value > 0 else None


def _download_entry(record: dict[str, Any], language: str) -> dict[str, Any] | None:
    """The `dta_urls` entry for ``language``, or the first available.

    Falling back to the first entry is deliberate: a canton that publishes only
    in French should still be captured, and the language actually captured is
    recorded on the resource rather than assumed.
    """
    entries = record.get("dta_urls") or []
    for entry in entries:
        if entry.get("language") == language:
            return entry
    return entries[0] if entries else None


def _current_version(record: dict[str, Any]) -> dict[str, Any] | None:
    """The version record carrying temporal validity.

    Temporal fields live on `matches[]`, not on the text-of-law record — reading
    them from the root yields nothing at all, silently. Prefer the entry LexFind
    badges `current`; otherwise take the first.
    """
    matches = record.get("matches") or []
    for match in matches:
        if match.get("info_badge") == "current":
            return match
    return matches[0] if matches else None


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
    # Promoted from AWAITING_EVIDENCE on 2026-07-28 against three ADR-0030
    # acceptance runs, each `execution_mode: live` and each `skipped_gates=[]`, so
    # for these corpora the pass covers the whole gate set rather than a subset:
    #
    #   docs/runbooks/evidence/2026-07-22-ch-canton-zh-lexfind-acceptance-v3
    #     ZH — 4 PDFs (554.1 / 554.11 / 554.5 / 554.51), 4/4 through DI, 9 hits
    #   docs/runbooks/evidence/2026-07-28-ch-canton-be-lexfind-acceptance
    #     BE — 2 PDFs (916.31 Hundegesetz, 916.812 THV), 2/2 through DI, 1 hit
    #   docs/runbooks/evidence/2026-07-28-ch-canton-bs-lexfind-acceptance
    #     BS — 5 PDFs (365.100 / .110 / .101 + two communal), 5/5 through DI, 7 hits
    #
    # Three cantons, three systematic-numbering schemes, one unchanged provider.
    # That is the evidence the promotion rests on: it is not one corpus generalised.
    #
    # This key says the CODE works. The config key — whether a corpus is accepted —
    # is the operator's, and every lexfind template still ships `enabled: false`.
    #
    # What is still NOT verified: coverage. Every current template enumerates via
    # search, so a live run proves the branch it asked for, never the canton's
    # corpus.
    #
    # That is a property of the strategy, not of LexFind. Measured 2026-07-28:
    # `/texts-of-law/{id}` answers densely over 1..~35000 (404 past the end) and
    # each record carries entity, systematic_number, is_active and the PDF — so an
    # id sweep reaches the whole corpus without touching search, and
    # `entities/extended` publishes per-entity counts (ZH 1377/944 active; 33314
    # total across 28 entities) to verify it against. #816 tracks both.
    #
    # An earlier version of this comment read "a branch is not a corpus", implying
    # the corpus was expensive. It is not; the search endpoint just cannot reach it.
    #
    # If this is ever rolled back, roll back to SCAFFOLD, not AWAITING_EVIDENCE:
    # the latter is the one state whose acceptance runs waive the operator's config
    # key, so it would re-open the route a rollback is trying to close.
    readiness = AcquisitionReadiness.LIVE

    def plan(self, source: Source, source_version: SourceVersion) -> ProviderPlan:
        spec = source_version.acquisition_spec or {}
        language = spec.get("language") or _DEFAULT_LANGUAGE
        entity_ids = list(spec.get("entity_ids") or [])
        page_size = int(spec.get("results_per_page") or _DEFAULT_PAGE_SIZE)
        max_pages = int(spec.get("max_pages") or _MAX_PAGES)

        search_text = str(spec.get("search_text") or "").strip()

        enumeration = str(spec.get("enumeration") or "").strip()
        enumerating = enumeration == _ENUMERATION_STRATEGY_DIGIT_UNION

        notes = [
            "Capture path verified live (#716): /tol/{id}/{lang} returns "
            "application/pdf, md5-identical to the canton's own file.",
            "Search contract verified live 2026-07-22: all 11 fields required, "
            "results under `texts_of_law_with_matches`, dates DD.MM.YYYY.",
        ]
        if enumerating:
            notes.append(
                "ENUMERATION: digit union over systematic numbers (0-9, deduplicated "
                "by tol id), which is the whole corpus for the scoped entities rather "
                "than a branch. Verified on ZH 2026-07-28: 1377 unique records against "
                "a published total of 1377, in ~40 requests. The run reconciles itself "
                "against entities/extended and reports observed/expected/gap (#816)."
            )
            notes.append(
                "Repealed law IS included (active_only=False). ZH's 1377 carries 433 "
                "repealed acts; enumerating active-only would reconcile against 944 and "
                "silently drop a third of the corpus."
            )
        else:
            notes.append(
                "COVERAGE LIMIT: this template enumerates via search, and the search "
                "endpoint has no list-everything call — `search_text` must be non-empty. "
                "So a run covers the branch it asked for ('554' + entity 26 returns the "
                "ZH animal-protection branch), not the canton's corpus. This is a limit "
                "of the CHOSEN STRATEGY, not of the source: set "
                f"`enumeration: {_ENUMERATION_STRATEGY_DIGIT_UNION}` to hold the whole "
                "corpus and have the run prove it against the published count (#816)."
            )
        if enumeration and not enumerating:
            notes.append(
                f"BLOCKING: acquisition_spec.enumeration '{enumeration}' is not a "
                f"supported strategy — the only one is "
                f"'{_ENUMERATION_STRATEGY_DIGIT_UNION}'."
            )
        if not search_text and not enumerating:
            notes.append(
                "BLOCKING: acquisition_spec.search_text is missing — this run "
                "would be refused before any request is made."
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
        search_text = str(spec.get("search_text") or "").strip()
        page_size = int(spec.get("results_per_page") or _DEFAULT_PAGE_SIZE)
        max_pages = int(spec.get("max_pages") or _MAX_PAGES)
        max_documents = int(spec.get("max_documents") or 0)
        min_pdf_bytes = int(spec.get("min_pdf_bytes") or _DEFAULT_MIN_PDF_BYTES)
        timeout_seconds = float(spec.get("request_timeout_seconds") or 20.0)

        coverage: dict[str, Any] | None = None
        resources: list[ProviderResource] = []
        skipped: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []

        enumeration = str(spec.get("enumeration") or "").strip()
        if enumeration and enumeration != _ENUMERATION_STRATEGY_DIGIT_UNION:
            return ProviderStartResult(
                external_job_id=f"lexfind-{run.run_id}",
                provider=self.provider_name,
                request_payload={"language": language, "entity_ids": entity_ids},
                response_payload={"captured": 0, "skipped": [], "failures": []},
                inline_resources=[],
                inline_failure_reason=(
                    f"acquisition_spec.enumeration '{enumeration}' is not supported — "
                    f"the only strategy is '{_ENUMERATION_STRATEGY_DIGIT_UNION}'."
                ),
            )
        enumerating = enumeration == _ENUMERATION_STRATEGY_DIGIT_UNION
        if enumerating and not entity_ids:
            # Without a scope this would enumerate all 28 entities — ~33 000 texts
            # of law — from a config that looks like every other template.
            return ProviderStartResult(
                external_job_id=f"lexfind-{run.run_id}",
                provider=self.provider_name,
                request_payload={"language": language, "entity_ids": []},
                response_payload={"captured": 0, "skipped": [], "failures": []},
                inline_resources=[],
                inline_failure_reason=(
                    "acquisition_spec.entity_ids is required when enumeration is "
                    f"'{_ENUMERATION_STRATEGY_DIGIT_UNION}' — an unscoped sweep would "
                    "pull every entity LexFind carries."
                ),
            )

        if not search_text and not enumerating:
            # Fail here rather than send a request the API will reject: an empty
            # `search_text` is a 400, and a spec missing it is a configuration
            # error the operator must see named, not a transport failure.
            return ProviderStartResult(
                external_job_id=f"lexfind-{run.run_id}",
                provider=self.provider_name,
                request_payload={"language": language, "entity_ids": entity_ids},
                response_payload={"captured": 0, "skipped": [], "failures": []},
                inline_resources=[],
                inline_failure_reason=(
                    "acquisition_spec.search_text is required and must be non-empty — "
                    "LexFind has no list-everything call. Use a systematic-number "
                    "prefix (e.g. '554' with entity_ids [26] returns the ZH "
                    "animal-protection branch)."
                ),
            )

        async with httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            try:
                if enumerating:
                    records = await self._enumerate_digit_union(
                        client,
                        language=language,
                        entity_ids=entity_ids,
                        category_ids=category_ids,
                        page_size=page_size,
                        max_pages=max_pages,
                    )
                else:
                    records = await self._discover(
                        client,
                        language=language,
                        search_text=search_text,
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
                records = []

            # Reconcile against the published denominator. Only meaningful for an
            # enumeration: a search covers a branch, and comparing a branch to the
            # canton's total would manufacture a coverage gap that is not one.
            if enumerating:
                try:
                    totals = await self._entity_totals(client, language=language)
                except Exception as exc:  # noqa: BLE001 — a missing denominator is
                    # recorded as unknown, never as complete.
                    failures.append(
                        {"url": f"{_API_PREFIX}/{language}/{_ENTITIES_PATH}", "error": str(exc)}
                    )
                else:
                    coverage = self._reconcile(records, entity_ids=entity_ids, totals=totals)

            if max_documents and len(records) > max_documents:
                # A cap makes the run a sample, so the coverage claim has to stop
                # being a completeness claim — otherwise `complete: true` from the
                # enumeration would sit next to a fraction of the documents.
                if coverage is not None:
                    coverage["truncated_by_max_documents"] = True
                    coverage["complete"] = False
                records = records[:max_documents]

            for record in records:
                tol_id = record.get("id")
                try:
                    resource = await self._capture(
                        client,
                        tol_id=tol_id,
                        record=record,
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
                **({"coverage": coverage} if coverage is not None else {}),
            },
            inline_resources=resources,
            inline_failure_reason=failures[0]["error"] if failures and not resources else None,
        )

    async def _discover(
        self,
        client: httpx.AsyncClient,
        *,
        language: str,
        search_text: str,
        entity_ids: list[int],
        category_ids: list[int],
        page_size: int,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        """Return full texts-of-law records for the requested search.

        **There is no "list everything" call.** `search_text` must be non-empty
        (verified: `""` returns 400), so discovery is always a query, never an
        enumeration. The workable strategy — also verified — is a **systematic
        number prefix** with `search_in_systematic_number`: `"554"` scoped to
        entity 26 returns the whole ZH animal-protection branch, all four acts,
        in one call:

            22888  554.51  Hundeverordnung
            22871  554.5   Hundegesetz
            21954  554.11  Kantonale Tierschutzverordnung
            22765  554.1   Kantonales Tierschutzgesetz

        Full-corpus coverage therefore means iterating prefixes, not one sweep.
        That is a real limitation of this API and is recorded rather than papered
        over; `plan()` reports it.

        Records are returned whole because the search response already carries
        the download URL, the canton's `original_url` and the version's temporal
        fields — re-fetching each `texts-of-law/{id}` would double the request
        count for data already in hand.
        """
        payload = dict(_SEARCH_PAYLOAD_TEMPLATE)
        payload["search_text"] = search_text
        payload["entity_filter"] = entity_ids
        payload["category_filter"] = category_ids
        return await self._search_once(
            client,
            language=language,
            payload=payload,
            page_size=page_size,
            max_pages=max_pages,
        )

    async def _search_once(
        self,
        client: httpx.AsyncClient,
        *,
        language: str,
        payload: dict[str, Any],
        page_size: int,
        max_pages: int,
        seen: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Open one search and page it out, deduplicating by `tol id`.

        `seen` is shared across calls by the digit-union enumeration so that a
        record matched by several digits is captured once. Passing None keeps the
        per-search behaviour a single query needs.
        """
        opened = await client.post(f"{_API_PREFIX}/{language}/fulltext-search", json=payload)
        opened.raise_for_status()
        session = opened.json()
        search_id = session.get("id")
        session_id = session.get("session_id")
        if search_id is None:
            return []

        records: list[dict[str, Any]] = []
        if seen is None:
            seen = set()
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
            body = page.json()
            rows = body.get(_RESULTS_KEY) or []
            for row in rows:
                tol_id = row.get("id")
                if isinstance(tol_id, int) and tol_id not in seen:
                    seen.add(tol_id)
                    records.append(row)
            if page_no >= int(body.get("number_of_pages") or 1):
                break
        return records

    async def _enumerate_digit_union(
        self,
        client: httpx.AsyncClient,
        *,
        language: str,
        entity_ids: list[int],
        category_ids: list[int],
        page_size: int,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        """Return EVERY text of law for the scoped entities, not a branch.

        Ten queries — one per digit — unioned and deduplicated. See the
        `_ENUMERATION_*` constants for why the union is complete and why the sum
        is not, and why `active_only` must stay False.

        The `seen` set is shared across all ten so overlap costs pages, not
        duplicates: on ZH the ten queries report 2613 hits and yield 1377 records.
        """
        seen: set[int] = set()
        records: list[dict[str, Any]] = []
        for digit in _ENUMERATION_DIGITS:
            payload = dict(_ENUMERATION_PAYLOAD_TEMPLATE)
            payload["search_text"] = digit
            payload["entity_filter"] = entity_ids
            payload["category_filter"] = category_ids
            records.extend(
                await self._search_once(
                    client,
                    language=language,
                    payload=payload,
                    page_size=page_size,
                    max_pages=max_pages,
                    seen=seen,
                )
            )
        return records

    @staticmethod
    def _reconcile(
        records: list[dict[str, Any]],
        *,
        entity_ids: list[int],
        totals: dict[int, dict[str, int]],
    ) -> dict[str, Any]:
        """Observed vs published, per entity — the coverage ledger's raw material.

        `complete` is only ever True when every scoped entity has a published
        denominator AND observed equals it. An entity LexFind does not report is
        `expected: None` and makes the whole run incomplete: an unknown
        denominator must never round up to full coverage (#816).
        """
        observed: dict[int, int] = {}
        for record in records:
            entity_id = (record.get("entity") or {}).get("id")
            if isinstance(entity_id, int):
                observed[entity_id] = observed.get(entity_id, 0) + 1

        entities: list[dict[str, Any]] = []
        complete = True
        for entity_id in entity_ids:
            published = totals.get(entity_id)
            expected = published.get("total") if published else None
            found = observed.get(entity_id, 0)
            if expected is None or found != expected:
                complete = False
            entities.append(
                {
                    "entity_id": entity_id,
                    "expected": expected,
                    "observed": found,
                    "gap": None if expected is None else expected - found,
                    "changed_last_30d": published.get("changed_last_30d") if published else None,
                }
            )

        return {
            "strategy": _ENUMERATION_STRATEGY_DIGIT_UNION,
            "denominator_tier": DenominatorTier.PUBLISHED.value,
            "denominator_source": f"{_API_PREFIX}/{{lang}}/{_ENTITIES_PATH}",
            "complete": complete,
            "entities": entities,
        }

    async def _entity_totals(
        self, client: httpx.AsyncClient, *, language: str
    ) -> dict[int, dict[str, int]]:
        """Published per-entity counts — the denominator a sweep is checked against.

        This is what makes coverage a measurement rather than a hope: the run
        reports `observed` against `expected` and the gap, instead of reporting
        success for whatever it happened to find (#816).
        """
        response = await client.get(
            f"{_API_PREFIX}/{language}/{_ENTITIES_PATH}", params={"n_days": 30}
        )
        response.raise_for_status()
        totals: dict[int, dict[str, int]] = {}
        for entity in response.json() or []:
            entity_id = entity.get("id")
            status = entity.get("status") or {}
            if isinstance(entity_id, int):
                totals[entity_id] = {
                    # `or 0` here was a live defect. A reported entity whose
                    # `total_texts_of_law` is missing or zero became `expected: 0`, and
                    # `_reconcile` then compared `found == 0` against `expected == 0` and
                    # left `complete: True` — "this canton publishes zero laws and we hold
                    # all zero of them". That is the fabricated completeness claim this
                    # module exists to prevent, arriving through a door
                    # `test_unknown_denominator_never_rounds_up_to_complete` does not
                    # cover: it exercises the ABSENT entity, not the empty count.
                    #
                    # Zero is not a denominator. A source claiming to publish no law at
                    # all is unstatable, not complete.
                    "total": _positive_int_or_none(status.get("total_texts_of_law")),
                    "active": _positive_int_or_none(status.get("active_texts_of_law")),
                    "changed_last_30d": int(status.get("changes_in_last_n_days") or 0),
                }
        return totals

    async def _capture(
        self,
        client: httpx.AsyncClient,
        *,
        tol_id: int,
        record: dict[str, Any],
        language: str,
        run: Run,
        min_pdf_bytes: int,
        skipped: list[dict[str, Any]],
    ) -> ProviderResource | None:
        """Fetch one text of law as PDF, guarded, with its temporal window."""
        dta = _download_entry(record, language)
        pdf_url = (dta or {}).get("url") or f"/tol/{tol_id}/{language}"

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
        # `original_url` lives on the download entry, not the record root, and is
        # what keeps the canonical citation pointing at the canton rather than at
        # the mirror.
        original_url = (dta or {}).get("original_url")
        if original_url:
            metadata["original_url"] = original_url
        if record.get("systematic_number"):
            metadata["systematic_number"] = record["systematic_number"]
        entity = record.get("entity") or {}
        if entity.get("id") is not None:
            metadata["lexfind_entity_id"] = entity["id"]
            metadata["lexfind_entity"] = entity.get("abbreviation")

        # Temporal validity is on the VERSION record, not the text-of-law record.
        version = _current_version(record)
        if version:
            metadata["lexfind_version_id"] = version.get("id")
            if version.get("info_badge"):
                metadata["lexfind_info_badge"] = version["info_badge"]
        metadata.update(temporal_metadata(version or {}))

        in_force = is_in_force(version or record)
        if in_force is not None:
            metadata["in_force"] = in_force

        title = (version or {}).get("title") or record.get("title")

        return ProviderResource(
            source_url=original_url or f"{_BASE_URL}{pdf_url}",
            final_url=f"{_BASE_URL}{pdf_url}",
            content_type="application/pdf",
            body_bytes=body,
            title=title,
            http_status=pdf.status_code,
            discovery_depth=0,
            metadata=metadata,
        )
