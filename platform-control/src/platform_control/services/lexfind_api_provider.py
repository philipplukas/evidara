"""LexFind API provider — cantonal legislation for 26 cantons + Bund (#731).

LexFind (`www.lexfind.ch`, a project of the *Schweizerische
Staatsschreiberkonferenz*) exposes an unauthenticated JSON API over the same
texts of law the cantons publish themselves. It exists here because in 2026-07
the obvious design — scraping each canton's own portal — could not work for
Zürich, and #716 measured why: the ZH-Lex `erlass-*.html` page is metadata-only
(`§ = 0` on all 18 sampled pages, 1879→2026), its only text link points at
`www.notes.zh.ch`, which was then refusing TCP on 443 and 80, and the canton's
own search API returned 503/204 for every filter parameter.

**That was a snapshot, and it has expired.** Re-measured 2026-09-03:
`www.notes.zh.ch` answers on 443 and 80 (`Server: Lotus-Domino`), the full direct
path works end to end — erlass page → a 154-byte JS stub → `WebView/$File/` →
`200 application/pdf`, 84 740 bytes, `%PDF-1.4`, 42 `§` markers — the ZH sitemap
404s on 0/20 sampled entries (was ~5/18), and the search API returns 200 with
correct results on every filter. Do not quote the paragraph above as a live fact.

The mirror is kept anyway, and the outage is the argument for it rather than
against: LexFind covers 26 cantons for a third of the requests, is LIVE on banked
evidence, and stayed up through the exact seven weeks the canton's own host was
refusing connections. What the outage does *not* buy is an exemption from the
product principle — Evidara acquires from the issuing source and keeps full
source provenance — so a mirror is only admissible while we keep proving it
equals the source. See the next section for how that proof is now kept live.

One provider covers the cantonal rung for all 28 entities, which is the point:
#628 measures *the cost of the Nth source*, and 28 jurisdictions behind one
homogeneous contract is the cheapest available test of whether that cost falls.

PROVENANCE IS PROVABLE, NOT ASSERTED
------------------------------------
LexFind is a mirror, and a mirror needs justifying. #716 verified the mirrored
file is byte-identical to the canton's own, and 2026-09-03 re-verified it from
both live sides (`cmp`-identical):

    461c614535cb7b5aa33175904f7d3229  the official notes.zh.ch file
    461c614535cb7b5aa33175904f7d3229  LexFind /tol/22871/de, fetched live

Two things keep that from decaying into a claim in a comment:

  * **Provenance cannot degrade to the mirror.** A record whose `original_url`
    is missing is REFUSED, with the slug `original_url_missing`, rather than
    captured with the LexFind URL substituted as its source. See :meth:`_capture`.
  * **Byte-identity is re-checked, not remembered.** :func:`verify_mirror_fidelity`
    fetches the canton's own file for a small *sample* of each run's captures and
    compares md5. A divergence fails the run. See the section below.

Every record also carries `original_url` back to the canton's own page, so the
canonical citation survives the mirror.

THE MIRROR SPOT-CHECK (#731)
----------------------------
The gap this closes is **independence**, not provenance: nothing would have
noticed if LexFind stopped mirroring faithfully, because the identity was
asserted once, in prose, in 2026-07.

It is a *sample*, deliberately, and not a second fetch per capture. Doubling
every acquisition's request count against a public-sector service is not an
acceptable price for the check, so the posture from #797 holds: one request at a
time, seconds apart, an identifying User-Agent (its own — the canton is told what
is knocking, not the name of the mirror being checked), a handful of requests per
run. Defaults are `mirror_spot_check_sample: 1` and
`mirror_spot_check_delay_seconds: 3.0`; `0` disables it. Both are clamped —
config may tune the politeness, not defeat it — and the delay is applied before
EVERY request to the canton, not merely between sampled documents.

Four outcomes, and the difference between them is the whole design:

  * ``identical`` — the canton's file and the mirrored bytes have the same md5.
  * ``diverged`` — they do not. **This fails the run and discards the whole batch
    unpublished.** Failing the run alone would not be enough: `_dispatch_run`
    persists and publishes inline resources before it reads the failure reason,
    so a check that flagged a divergence while still handing the documents down
    would put the divergent corpus in the index, cited to the canton's own URL,
    and make the corpus worse than not checking at all. The unsampled documents
    are discarded with the sampled one: a mirror that has stopped being faithful
    is not trustworthy for the records we happened not to draw.
  * ``source_unreachable`` / ``source_document_not_found`` — the canton's host
    did not answer, or its page did not lead to a document. Recorded and
    **warned about**, but NOT a failure. Seven weeks of #716 are the reason: an
    unreachable canton is the condition the mirror exists to survive, and failing
    runs on it would hand the outage the power the mirror was chosen to deny it.
    A run whose every sampled document came back unverified says so loudly — that
    is the state in which the mirror is trusted on assertion again.
  * ``check_error`` — this code raised. Kept distinct from an outage on purpose:
    a regression in the resolver would otherwise render the check permanently
    inert while reporting the same slug as a canton that is merely down.

The resolver spends at most a handful of requests per document, across all hops
and all candidate links, and considers at most a few candidates per page. It is
not a crawler and must not become one; if a canton needs bespoke traversal, that
is an argument for a direct provider, not for widening this.

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

import asyncio
import hashlib
import logging
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import httpx

from acquisition_core.artifact_guard import check_capture, has_format_magic, looks_like_html
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

# Mirror spot-check (#731). Conservative on purpose: one sampled document per
# run, with the pace applied before every request to the canton, is the #797
# posture. `0` disables the check entirely.
_DEFAULT_MIRROR_SPOT_CHECK_SAMPLE = 1
_DEFAULT_MIRROR_SPOT_CHECK_DELAY_SECONDS = 3.0

# Hard ceilings. An acquisition spec is operator-supplied config, and without a
# cap `{"mirror_spot_check_sample": 5000, "mirror_spot_check_delay_seconds": 0}`
# is a plausible-looking typo that turns a verifier into thousands of unpaced
# requests at a cantonal host. The knobs tune politeness; they may not defeat it.
_MAX_MIRROR_SPOT_CHECK_SAMPLE = 5
_MAX_MIRROR_SPOT_CHECK_DELAY_SECONDS = 60.0

# Total requests the resolver may spend reaching ONE document, across all hops
# and all candidate links. Three is the measured ZH path (erlass page -> JS stub
# -> `WebView/$File/`); the fourth buys exactly one retry when a candidate is a
# dead end. This is the crawler ceiling and it is deliberately tight.
_MIRROR_SPOT_CHECK_MAX_REQUESTS = 4

# At most this many candidate links are considered per page. A page offering
# more than a handful is not a document landing page, and following them all is
# crawling.
_MIRROR_SPOT_CHECK_MAX_CANDIDATES_PER_PAGE = 3

# Candidate document links, ordered by how specific the TARGET is — not by the
# shape of the markup carrying it. Ordering by markup shape was a real hazard:
# a `window.location.href = …` pattern searched over the whole page wins
# globally, so any cookie banner, language switch or analytics snippet on a
# modern cantonal page is followed instead of the document.
#
# Note the first two also match `window.location.href='…'`, because `.href=` is
# `href\s*=`. So the #716 JavaScript stub is still resolved by pattern 1 or 2
# whenever its target looks like a document, and pattern 3 — any JS redirect at
# all — is the last resort it should always have been.
_SOURCE_LINK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""href\s*=\s*['"]([^'"]*/\$[Ff]ile/[^'"]+)['"]"""),
    re.compile(r"""href\s*=\s*['"]([^'"]+\.pdf(?:\?[^'"]*)?)['"]""", re.IGNORECASE),
    re.compile(r"""window\.location\.href\s*=\s*['"]([^'"]+)['"]""", re.IGNORECASE),
)

_MIRROR_STATUS_IDENTICAL = "identical"
_MIRROR_STATUS_DIVERGED = "diverged"
_MIRROR_STATUS_SOURCE_UNREACHABLE = "source_unreachable"
_MIRROR_STATUS_SOURCE_DOCUMENT_NOT_FOUND = "source_document_not_found"
# The check itself broke — a bug here, not a fact about the canton. Kept distinct
# from the two above so a regression in the resolver cannot hide as an outage.
_MIRROR_STATUS_CHECK_ERROR = "check_error"

_MIRROR_STATUSES_UNVERIFIED = (
    _MIRROR_STATUS_SOURCE_UNREACHABLE,
    _MIRROR_STATUS_SOURCE_DOCUMENT_NOT_FOUND,
    _MIRROR_STATUS_CHECK_ERROR,
)

# The canton is a different host with a different operator; it is told what is
# actually knocking, not the name of the mirror we happen to be checking.
_MIRROR_CHECK_USER_AGENT = "evidara-mirror-check/1.0 (+https://evidara.ai)"

# Temporal validity (#731, and the #661 trap it avoids).
#
# LexFind models repeal SEPARATELY from consolidation date. That is the whole
# reason this source is preferable for temporal questions: Fedlex was measured
# (#661) to leave `dateEndApplicability` open on the newest consolidation of works
# whose `inForceStatus` is "No longer in force", so consolidation dates alone
# report repealed law as currently in force. Here `version_inactive_since` is its
# own field and cannot be masqueraded by an open-ended newest version.
#
# THE BOUNDARY (#843). `version_inactive_since` is **EXCLUSIVE** — the first day
# the act is NO LONGER in force, not the last day it was. This is measured, not
# inferred from the field name:
#
#   1. It is null on every superseded version. `GET /api/frontend/v1/de/
#      texts-of-law/22871/with-version-groups` (ZH Hundegesetz, 2026-09-03)
#      returns 7 versions — active_since 01.01.1987, 01.01.2007 ×3, 01.01.2010,
#      01.01.2023, 01.06.2025 — and `version_inactive_since` is `null` on ALL of
#      them, including the six that are `is_active: false`. So the field is not a
#      version-window end at all; it is the **repeal date of the act**, which is
#      why it is mirrored by `info_badge: abrogated` + `info_badge_date`.
#   2. Its values are repeal EFFECTIVE dates. `GET /entities/{26,1}/recent-changes`
#      (ZH + BE, 5 pages each, 2026-09-03) yielded 150 changes of which 27 carry a
#      non-null `version_inactive_since`. **26 of 27 fall on the 1st of a month**
#      (01.05.2026, 01.06.2026, 01.07.2026, 01.08.2026, 01.09.2026, …); the lone
#      exception is 02.06.2018. NOT ONE is a month-end. Swiss repeals take effect
#      at the start of a month, so a field holding the *last day in force* would
#      cluster on 30/31 — this one holds the day the repeal took effect.
#   3. LexFind's own UI renders it under the i18n key
#      `text_of_law.info_badge.abrogated_since` — "abrogated **since** X".
#
# `version_active_since` is the mirror image and is inclusive, so a LexFind window
# is the half-open interval [version_active_since, version_inactive_since).
#
# Our boundary contract is the CLOSED one: `in_force_until` is the inclusive last
# day in force (contracts/schemas/document.schema.json, and
# legal-search/api/src/core/norm-hierarchy/in-force.ts:24-28). LexFind is the only
# one of the four providers whose upstream disagrees — ris_ogd and fedlex_sparql
# were both measured inclusive (see their own field constants) — so this provider,
# and only this provider, converts. See `_inclusive_end_date`.
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


def _inclusive_end_date(exclusive_iso: str | None) -> str | None:
    """Convert an EXCLUSIVE upstream end-date to our INCLUSIVE `in_force_until`.

    LexFind's `version_inactive_since` is the first day the act is no longer in
    force (measured — see `_LEXFIND_IN_FORCE_UNTIL_FIELD`). Our boundary contract
    is closed: `in_force_until` is the LAST day it WAS in force. The two differ by
    exactly one day, and shipping the raw value is a one-day error in the
    dangerous direction — `resolveInForceState` repeals only on `asOf > until`, so
    an unconverted date reports a repealed norm as good law on its repeal date.

    Returns None for an unparseable input, on the same rule as `_iso_date_or_none`:
    a mangled boundary is worse than an absent one, because absence resolves to
    `unknown` and a wrong date resolves confidently to the wrong answer.
    """
    if exclusive_iso is None:
        return None
    try:
        parsed = date.fromisoformat(exclusive_iso)
    except ValueError:
        logger.warning("lexfind: unparseable end date %r — dropped", exclusive_iso)
        return None
    return (parsed - timedelta(days=1)).isoformat()


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

    **The end-date is converted, not passed through (#843).** LexFind's
    `version_inactive_since` is exclusive and `in_force_until` is inclusive, so
    the emitted value is one day earlier — see `_inclusive_end_date`. This is the
    one provider of the four that converts; `ris_ogd` and `fedlex_sparql` were
    measured to publish an inclusive end-date already, so converting them would
    introduce the very off-by-one this fixes here.

    `is_active: False` with no `version_inactive_since` is recorded as
    `amendment_relation: repealed_by` WITHOUT inventing an end date: we know it
    is no longer in force, and we do not know when it stopped. Those are
    different facts and collapsing them is the #661 failure in the other
    direction.
    """
    out: dict[str, str] = {}
    since = _iso_date_or_none(record.get(_LEXFIND_IN_FORCE_FROM_FIELD))
    until = _inclusive_end_date(_iso_date_or_none(record.get(_LEXFIND_IN_FORCE_UNTIL_FIELD)))
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

    `as_of` is not optional in spirit. The answer is only ever true *on a date*,
    so acquisition passes the capture date explicitly and stores the result under
    a capture-scoped key; the default of "today" is a convenience for tests and
    ad-hoc inspection, not a licence to freeze the answer into a document.
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


@dataclass(frozen=True, slots=True)
class MirrorFidelityResult:
    """One document's answer to "does the mirror still equal the source?".

    ``status`` is a stable machine-readable slug, following
    :class:`acquisition_core.artifact_guard.GuardResult`'s vocabulary rather than
    inventing a second one: it is written into the run's response payload and read
    by an operator deciding whether the mirror is still admissible.

    The two md5s are both recorded even when they agree, because "we checked and
    they matched" is the evidence; "no divergence reported" is not.
    """

    status: str
    source_url: str
    tol_id: int | None = None
    mirror_md5: str | None = None
    source_md5: str | None = None
    source_document_url: str | None = None
    detail: str | None = None

    @property
    def diverged(self) -> bool:
        return self.status == _MIRROR_STATUS_DIVERGED

    def as_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"status": self.status, "source_url": self.source_url}
        for key, value in (
            ("tol_id", self.tol_id),
            ("mirror_md5", self.mirror_md5),
            ("source_md5", self.source_md5),
            ("source_document_url", self.source_document_url),
            ("detail", self.detail),
        ):
            if value is not None:
                record[key] = value
        return record


def _bounded_spec_int(value: Any, *, default: int, maximum: int) -> int:
    """An operator-supplied count, clamped into a range the host can survive.

    Raises ``ValueError`` with an operator-readable message rather than letting
    `int()` throw an unnamed one out of `start_run`; a malformed spec is a
    configuration refusal, not a transport failure.
    """
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected a whole number, got {value!r}") from exc
    return max(0, min(number, maximum))


def _bounded_spec_float(value: Any, *, default: float, maximum: float) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected a number, got {value!r}") from exc
    return max(0.0, min(number, maximum))


def source_link_candidates(body: bytes) -> list[str]:
    """Links on a canton page that plausibly lead to the document, best first.

    A LIST, not a first match. First-match-wins was a real hazard: the pattern
    for a JavaScript redirect matches anywhere on the page, so a cookie banner or
    a language switch on a modern cantonal page would be followed instead of the
    document — and with nothing to fall back to, the run recorded
    `source_document_not_found` and said nothing. Ordering by target specificity
    fixes the common case; returning alternatives fixes the rest.

    Capped at :data:`_MIRROR_SPOT_CHECK_MAX_CANDIDATES_PER_PAGE`. A page offering
    more than a handful is not a document landing page, and following them all is
    crawling — which this module has no permission to do.
    """
    text = body.decode("utf-8", errors="ignore")
    candidates: list[str] = []
    for pattern in _SOURCE_LINK_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group(1)
            if candidate not in candidates:
                candidates.append(candidate)
            if len(candidates) >= _MIRROR_SPOT_CHECK_MAX_CANDIDATES_PER_PAGE:
                return candidates
    return candidates


async def _resolve_source_document(
    client: httpx.AsyncClient,
    page_url: str,
    *,
    max_requests: int = _MIRROR_SPOT_CHECK_MAX_REQUESTS,
    pace: Callable[[], Awaitable[None]] | None = None,
) -> tuple[bytes, str] | None:
    """Walk from a canton's page to its actual document, or give up.

    Returns ``(body, url)`` for the first response whose bytes carry a PDF
    signature, or ``None`` when the request budget runs out or nothing on the
    pages reached looks like a document link. The magic number is the authority,
    not the declared content type — #716's stub was served as a download and was
    154 bytes of JavaScript.

    Depth-first over the candidates of each page, bounded by ``max_requests``
    across the WHOLE resolution rather than per hop, so one bad candidate costs a
    request instead of the answer. ``pace`` is awaited before every request,
    including the first: the politeness posture belongs to the host being
    knocked on, not to the loop that happens to be iterating.
    """
    budget = max_requests
    frontier: list[str] = [page_url]

    while frontier and budget > 0:
        url = frontier.pop(0)
        if pace is not None:
            await pace()
        budget -= 1
        response = await client.get(url)
        response.raise_for_status()
        body = response.content
        if has_format_magic(body, "application/pdf") and not looks_like_html(body):
            return body, str(response.url)
        resolved_url = str(response.url)
        # Candidates from this page go to the FRONT: the document is more likely
        # one hop below the page we just read than beside an earlier dead end.
        frontier = [
            urljoin(resolved_url, candidate) for candidate in source_link_candidates(body)
        ] + frontier

    return None


async def verify_mirror_fidelity(
    client: httpx.AsyncClient,
    *,
    original_url: str,
    mirrored_body: bytes,
    tol_id: int | None = None,
    max_requests: int = _MIRROR_SPOT_CHECK_MAX_REQUESTS,
    pace: Callable[[], Awaitable[None]] | None = None,
) -> MirrorFidelityResult:
    """Compare the mirrored bytes against the issuing source's own file.

    An unreachable source is NOT a divergence. Conflating the two would make the
    canton's uptime a precondition for ingesting from the mirror that exists
    because the canton's uptime cannot be relied on — #716 was seven weeks long.

    A bug in this function is not an outage either. Only `httpx` failures become
    `source_unreachable`; anything else is `check_error`, logged with a
    traceback, so a regression in the resolver cannot masquerade as a canton that
    happens to be down and quietly render the check inert forever.
    """
    mirror_md5 = hashlib.md5(mirrored_body, usedforsecurity=False).hexdigest()
    try:
        resolved = await _resolve_source_document(
            client, original_url, max_requests=max_requests, pace=pace
        )
    except httpx.HTTPError as exc:
        # Includes HTTPStatusError: a 404 at the canton may mean the document
        # moved, which is a provenance signal rather than a clean outage. Both
        # are `unverified` and both are warned about by the caller; the detail
        # carries the distinction for whoever reads the payload.
        return MirrorFidelityResult(
            status=_MIRROR_STATUS_SOURCE_UNREACHABLE,
            source_url=original_url,
            tol_id=tol_id,
            mirror_md5=mirror_md5,
            detail=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 — our bug, reported as ours
        logger.exception(
            "lexfind mirror check raised while resolving %s — the check did NOT run",
            original_url,
        )
        return MirrorFidelityResult(
            status=_MIRROR_STATUS_CHECK_ERROR,
            source_url=original_url,
            tol_id=tol_id,
            mirror_md5=mirror_md5,
            detail=f"{type(exc).__name__}: {exc}",
        )

    if resolved is None:
        return MirrorFidelityResult(
            status=_MIRROR_STATUS_SOURCE_DOCUMENT_NOT_FOUND,
            source_url=original_url,
            tol_id=tol_id,
            mirror_md5=mirror_md5,
            detail=f"no document reached within {max_requests} requests of the source page",
        )

    source_body, source_document_url = resolved
    source_md5 = hashlib.md5(source_body, usedforsecurity=False).hexdigest()
    if source_md5 == mirror_md5:
        return MirrorFidelityResult(
            status=_MIRROR_STATUS_IDENTICAL,
            source_url=original_url,
            tol_id=tol_id,
            mirror_md5=mirror_md5,
            source_md5=source_md5,
            source_document_url=source_document_url,
        )

    return MirrorFidelityResult(
        status=_MIRROR_STATUS_DIVERGED,
        source_url=original_url,
        tol_id=tol_id,
        mirror_md5=mirror_md5,
        source_md5=source_md5,
        source_document_url=source_document_url,
        detail=(
            f"mirror {len(mirrored_body)} bytes / md5 {mirror_md5} != "
            f"source {len(source_body)} bytes / md5 {source_md5}"
        ),
    )


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

        try:
            mirror_sample = _bounded_spec_int(
                spec.get("mirror_spot_check_sample"),
                default=_DEFAULT_MIRROR_SPOT_CHECK_SAMPLE,
                maximum=_MAX_MIRROR_SPOT_CHECK_SAMPLE,
            )
        except ValueError:
            mirror_sample = -1  # planned as malformed; start_run refuses it by name

        notes = [
            "Capture path verified live (#716): /tol/{id}/{lang} returns "
            "application/pdf, md5-identical to the canton's own file.",
            "Search contract verified live 2026-07-22: all 11 fields required, "
            "results under `texts_of_law_with_matches`, dates DD.MM.YYYY.",
            "PROVENANCE: a record LexFind publishes without `original_url` is "
            "REFUSED (`original_url_missing`), not captured with the mirror URL "
            "substituted as its source.",
        ]
        if mirror_sample < 0:
            notes.append(
                "BLOCKING: acquisition_spec.mirror_spot_check_sample is not a whole "
                "number — this run would be refused before any request is made."
            )
        elif mirror_sample > 0:
            notes.append(
                f"MIRROR SPOT-CHECK: {mirror_sample} captured document(s) per run are "
                "re-fetched from the CANTON's own host (up to "
                f"{_MIRROR_SPOT_CHECK_MAX_REQUESTS} requests each, paced) and compared "
                "by md5. A divergence FAILS the run AND DISCARDS the whole batch "
                "unpublished; an unreachable canton is recorded, warned about, and does "
                "not fail the run (the mirror exists to survive that — #716 lasted seven "
                "weeks). Set `mirror_spot_check_sample: 0` to disable, "
                f"`mirror_spot_check_delay_seconds` to pace it. Capped at "
                f"{_MAX_MIRROR_SPOT_CHECK_SAMPLE} documents per run."
            )
        else:
            notes.append(
                "MIRROR SPOT-CHECK DISABLED (`mirror_spot_check_sample: 0`): nothing in "
                "this run re-proves that LexFind still serves bytes identical to the "
                "issuing source. The identity is then an assertion, not a measurement."
            )
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
        # `0` disables the mirror spot-check; the default samples one document per
        # run. Read with an explicit None test rather than `or`, so a deliberate
        # `0` is honoured instead of falling back to the default. A malformed
        # value is a named configuration refusal, like every other spec error in
        # this method — never a raw ValueError out of `start_run`.
        try:
            mirror_sample = _bounded_spec_int(
                spec.get("mirror_spot_check_sample"),
                default=_DEFAULT_MIRROR_SPOT_CHECK_SAMPLE,
                maximum=_MAX_MIRROR_SPOT_CHECK_SAMPLE,
            )
            mirror_delay = _bounded_spec_float(
                spec.get("mirror_spot_check_delay_seconds"),
                default=_DEFAULT_MIRROR_SPOT_CHECK_DELAY_SECONDS,
                maximum=_MAX_MIRROR_SPOT_CHECK_DELAY_SECONDS,
            )
        except ValueError as exc:
            return ProviderStartResult(
                external_job_id=f"lexfind-{run.run_id}",
                provider=self.provider_name,
                request_payload={"language": language, "entity_ids": entity_ids},
                response_payload={"captured": 0, "skipped": [], "failures": []},
                inline_resources=[],
                inline_failure_reason=f"acquisition_spec: {exc}",
            )

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

        # Outside the LexFind client: these requests go to the CANTON, with their
        # own client, their own pacing and their own failure semantics.
        mirror_fidelity = await self._spot_check_mirror_fidelity(
            resources,
            run=run,
            sample_size=mirror_sample,
            delay_seconds=mirror_delay,
            timeout_seconds=timeout_seconds,
        )

        # A divergence outranks a transport failure as a reason to fail the run:
        # "some requests failed" is routine, "the mirror is no longer the source"
        # invalidates the reason this provider is allowed to exist.
        #
        # AND IT MUST DISCARD THE BATCH, not merely rename the run. `_dispatch_run`
        # persists `inline_resources` and builds the bundle events FIRST
        # (run_service.py:1320-1345); the `inline_failure_reason` block that
        # follows (:1348-1353) flips the run to FAILED, but
        # `_publish_pending_dispatch_events` (:1765-1787) publishes every
        # `raw_artifact.available` and `artifact_bundle.available` with no check on
        # `run.status`. Handing resources down alongside a failure reason therefore
        # ships the divergent corpus and marks the run red afterwards — the check
        # would make the corpus WORSE than not checking, since the documents land
        # cited to the canton's own URL. Every other provider in this repo gates on
        # `if not resources`, and _dispatch_run was written on that invariant.
        #
        # A whole-batch discard is the right blast radius, not just the diverged
        # document: a mirror that has stopped being faithful is not trustworthy for
        # the documents we happened not to sample.
        failure_reason: str | None = None
        published_resources = resources
        if mirror_fidelity and mirror_fidelity["diverged"]:
            discarded = len(resources)
            published_resources = []
            failure_reason = (
                f"mirror fidelity check FAILED for {mirror_fidelity['diverged']} of "
                f"{mirror_fidelity['sampled']} sampled document(s): LexFind no longer "
                "serves bytes identical to the issuing source. All "
                f"{discarded} captured document(s) were DISCARDED unpublished — the "
                "unsampled ones are no more trustworthy than the sampled one. Do not "
                "ingest from this mirror until the divergence is explained; see "
                "response_payload.mirror_fidelity."
            )
            logger.error(
                "lexfind run %s discarded %d captured document(s) unpublished: "
                "the mirror diverged from the issuing source",
                run.run_id,
                discarded,
            )
        elif failures and not resources:
            failure_reason = failures[0]["error"]

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
                # What was captured, which is not what was published when the
                # mirror check discarded the batch. Both numbers are recorded.
                "captured": len(resources),
                "published": len(published_resources),
                "skipped": skipped,
                "failures": failures,
                **({"coverage": coverage} if coverage is not None else {}),
                **({"mirror_fidelity": mirror_fidelity} if mirror_fidelity is not None else {}),
            },
            inline_resources=published_resources,
            inline_failure_reason=failure_reason,
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

        # PROVENANCE MAY NOT DEGRADE TO THE MIRROR.
        #
        # `original_url` is the canton's own page — the thing that makes a
        # mirrored capture admissible under "acquire from the issuing source and
        # keep full source provenance". This used to be `if original_url:`, with
        # `source_url=original_url or <the LexFind URL>` further down: when
        # LexFind omitted the field, the capture silently recorded the *mirror*
        # as the document's source and nothing said so. That is the quiet
        # substitution this repo refuses everywhere else (#631, #675, #713).
        #
        # Refusing rather than marking is deliberate. A marker would only live in
        # provider metadata, which no query reads: the document would enter the
        # corpus citing lexfind.ch as its source and nothing downstream could
        # tell it apart. A skip is ENFORCED — the document does not enter the
        # corpus at all — and it is named twice, in `response_payload.skipped`
        # and in the log.
        #
        # Note what the refusal does NOT do, since an earlier draft of this
        # comment claimed it: it does not show up in the coverage reconciliation.
        # `_reconcile` counts discovered RECORDS and runs before this loop, so a
        # record refused here still counts as observed — and coverage is computed
        # only for enumeration runs, so in search mode there is no coverage block
        # at all. That is why the log line below exists rather than being
        # redundant with a count somewhere else.
        #
        # Measured 2026-09-03: 100/100 sampled records across 21 cantons carry
        # `original_url`, so this closes a latent path rather than discarding law
        # we can actually reach.
        original_url = (dta or {}).get("original_url")
        if not original_url:
            logger.warning(
                "lexfind refused tol_id=%s (%s): no original_url, so capturing it would "
                "record the mirror as the document's own source",
                tol_id,
                record.get("systematic_number") or pdf_url,
            )
            skipped.append(
                {
                    "tol_id": tol_id,
                    "url": pdf_url,
                    "reason": "original_url_missing",
                    "detail": (
                        "LexFind published no original_url for this record; capturing it "
                        "would record the mirror as the document's source"
                    ),
                }
            )
            return None

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

        fetched_at = datetime.now(UTC)

        metadata: dict[str, Any] = {
            "provider": self.provider_name,
            "tol_id": tol_id,
            "language": language,
            "run_id": run.run_id,
            "fetched_at": fetched_at.isoformat(),
            "capture_guard": "passed",
            "legal_text_assessment": "abstained_binary_manifestation",
            "legal_text_evidence": assessment.as_evidence(),
        }
        # `original_url` lives on the download entry, not the record root, and is
        # what keeps the canonical citation pointing at the canton rather than at
        # the mirror. Its absence was refused above, so it is present here.
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

        # Point-in-time force is DERIVED from the window emitted just above, at
        # query time, by whoever is asking and for the date they are asking
        # about (`resolveInForceState` in legal-search, driven by `in_force_at`).
        # It is never read back from a stored boolean, because a boolean is only
        # true on the day it was computed and this corpus outlives its captures:
        # #661 IS a law that was in force when it was fetched and is not now.
        # This key used to be a bare `in_force`, which read as a claim about the
        # present and silently became a lie the first time a captured law was
        # repealed.
        #
        # What is honest to record is the capture-time *observation*, named so it
        # cannot be mistaken for the answer and pinned to the same instant as
        # `fetched_at` rather than to a second `now()`. Same SHAPE as
        # `fedlex_sparql`'s `in_force_at_selection` (fedlex_sparql_provider.py:306)
        # — a time-scoped observation rather than a timeless claim — but not the
        # same key, and therefore NOT covered by the same gate:
        # scripts/ch-fedlex-fast-loop.sh:643-645 filters on the literal name
        # `in_force_at_selection`, so it will never see this one. Unifying the two
        # names would let one gate cover both providers and is worth doing when
        # something other than that fedlex-shaped canary needs it; `capture` is
        # the accurate word here, because this provider selects no consolidation
        # member.
        #
        # `fetched_at` is UTC, so `as_of` is the UTC date. A capture made in
        # Switzerland between midnight and 01:00/02:00 local falls on the previous
        # UTC day and is therefore evaluated one day early against an exclusive
        # end boundary. Not introduced here — `is_in_force`'s default was already
        # UTC — but it is a real one-day error in a corpus of Swiss law. #843
        # settled the *boundary* (exclusive upstream, converted at
        # `temporal_metadata`) and deliberately did NOT touch this: the timezone of
        # `fetched_at` is a separate defect with a separate fix, and folding it in
        # would have made the boundary change unfalsifiable.
        in_force_at_capture = is_in_force(version or record, as_of=fetched_at.date().isoformat())
        if in_force_at_capture is not None:
            metadata["in_force_at_capture"] = in_force_at_capture

        title = (version or {}).get("title") or record.get("title")

        # DOCUMENT IDENTITY IS STATED HERE, NOT INFERRED DOWNSTREAM (#850).
        #
        # `source_url` is the canton's own page and its path embeds BOTH version
        # dates — `erlass-554_51-2009_11_25-2010_01_01-129.html` is enactment
        # 2009-11-25, in force 2010-01-01. It changes with every version, so
        # keying `document_id` on it mints a fresh searchable copy of the law at
        # each revision instead of superseding the previous one: the #652
        # duplicate mechanism, which is why it must not be the identity.
        #
        # It stays `source_url` regardless — provenance must keep pointing at the
        # canton, not at the mirror (the refusal above). Identity and provenance
        # are different questions and this provider is the case where they have
        # different answers; the global `source_url`-first rule could only ever
        # get one of the two providers right (see `acquisition_core.identity`).
        #
        # The identity is the text-of-law id, built from `tol_id` rather than from
        # the download entry's URL: `dta_urls[].url` happens to be `/tol/{id}/{lang}`
        # today, but `/tolv/{id}/{lang}` — the per-VERSION path — appears elsewhere
        # in the same payload (`matches[].dtah_urls`), so deriving identity from a
        # published URL is one upstream change away from being version-scoped again.
        # `tol_id` cannot be.
        #
        # The captured language is part of the identity because it is part of the
        # manifestation: `_download_entry` may fall back to another language than the
        # one requested, and the German and French texts of an act are different
        # documents in this corpus, not two copies of one.
        captured_language = str((dta or {}).get("language") or language)
        identity_locator = f"{_BASE_URL}/tol/{tol_id}/{captured_language}"

        return ProviderResource(
            source_url=original_url,
            final_url=f"{_BASE_URL}{pdf_url}",
            identity_locator=identity_locator,
            content_type="application/pdf",
            body_bytes=body,
            title=title,
            http_status=pdf.status_code,
            discovery_depth=0,
            metadata=metadata,
        )

    async def _spot_check_mirror_fidelity(
        self,
        resources: list[ProviderResource],
        *,
        run: Run,
        sample_size: int,
        delay_seconds: float,
        timeout_seconds: float,
    ) -> dict[str, Any] | None:
        """Re-prove the mirror against the issuing source, for a small sample.

        Returns ``None`` when the check is switched off or there is nothing to
        check, so the run's response payload gains a key only when a check was
        actually performed — an absent key must never read as "verified".

        The sample is drawn with the run id as seed: reproducible for a given run,
        and different across runs, so repeated acquisition of a corpus walks
        different documents instead of re-proving the same one forever.
        """
        if sample_size <= 0 or not resources:
            return None

        candidates = [r for r in resources if r.metadata.get("original_url") and r.body_bytes]
        if not candidates:
            return None

        rng = random.Random(str(run.run_id))  # noqa: S311 — sampling, not secrets
        sampled = rng.sample(candidates, k=min(sample_size, len(candidates)))

        # #797's posture, applied to the host it protects. This used to sleep
        # between sampled DOCUMENTS, which meant that at the shipped default of
        # one document the delay never ran at all, while `_resolve_source_document`
        # made up to three back-to-back requests. The pacer is now handed to the
        # resolver and awaited before EVERY request to the canton.
        pacer_state = {"first": True}

        async def pace() -> None:
            if pacer_state["first"]:
                pacer_state["first"] = False
                return
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

        checks: list[MirrorFidelityResult] = []
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
            headers={"User-Agent": _MIRROR_CHECK_USER_AGENT},
            follow_redirects=True,
        ) as source_client:
            for resource in sampled:
                checks.append(
                    await verify_mirror_fidelity(
                        source_client,
                        original_url=str(resource.metadata["original_url"]),
                        mirrored_body=resource.body_bytes or b"",
                        tol_id=resource.metadata.get("tol_id"),
                        pace=pace,
                    )
                )

        diverged = [check for check in checks if check.diverged]
        for check in diverged:
            # Loud, and in the logs as well as the payload: a mirror that has
            # stopped equalling its source is not a data-quality nit, it is the
            # premise of using the mirror at all.
            logger.error(
                "lexfind mirror diverged from the issuing source: tol_id=%s source=%s %s",
                check.tol_id,
                check.source_url,
                check.detail,
            )

        # An UNVERIFIED check is not a passed check, and a count buried in a job
        # payload is the "marker nothing reads" this provider refuses elsewhere.
        # Every one of them says so in the log.
        unverified = [check for check in checks if check.status in _MIRROR_STATUSES_UNVERIFIED]
        for check in unverified:
            logger.warning(
                "lexfind mirror NOT verified (%s): tol_id=%s source=%s %s",
                check.status,
                check.tol_id,
                check.source_url,
                check.detail,
            )
        if checks and not diverged and len(unverified) == len(checks):
            # Nothing in this run proved anything. Distinct from "one of three
            # was unreachable", and the state in which the mirror is running on
            # an assertion again — which is the condition this check exists to
            # end. Not a failure (the canton may simply be down, #716), but it
            # must never pass silently.
            logger.warning(
                "lexfind mirror fidelity UNPROVEN for run %s: all %d sampled document(s) "
                "were unverified. The mirror is being trusted on assertion, not measurement.",
                run.run_id,
                len(checks),
            )

        identical = sum(1 for c in checks if c.status == _MIRROR_STATUS_IDENTICAL)
        return {
            "sampled": len(sampled),
            "candidates": len(candidates),
            "identical": identical,
            "diverged": len(diverged),
            "unverified": len(unverified),
            # One boolean an operator can read without interpreting three counts:
            # did anything in this run actually prove the mirror equals the source?
            "proven": identical > 0 and not diverged,
            "checks": [check.as_record() for check in checks],
        }
