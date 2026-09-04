from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import httpx
import pytest

from platform_control.services.ris_ogd_provider import RisOgdProvider, _extract_metadata


class TimeoutingRisAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self) -> TimeoutingRisAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str, *, params=None):
        request = httpx.Request("GET", url, params=params)
        if url == "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht":
            return httpx.Response(
                200,
                json={
                    "OgdSearchResult": {
                        "OgdDocumentResults": {
                            "Hits": {"#text": "1"},
                            "OgdDocumentReference": {
                                "Data": {
                                    "Metadaten": {
                                        "Technisch": {
                                            "ID": "NOR11013238",
                                            "Applikation": "BrKons",
                                            "Organ": "Bundeskanzleramt",
                                        },
                                        "Allgemein": {
                                            "DokumentUrl": (
                                                "https://www.ris.bka.gv.at/"
                                                "Dokumente/Bundesnormen/NOR11013238/NOR11013238.html"
                                            )
                                        },
                                        "Bundesrecht": {
                                            "Titel": "Verordnung des Bundesministers",
                                            "Kurztitel": "Test-Verordnung",
                                            "Eli": "eli/bgbl/test",
                                        },
                                    },
                                    "Dokumentliste": {
                                        "ContentReference": {
                                            "ContentType": "MainDocument",
                                            "Urls": {
                                                "ContentUrl": [
                                                    {
                                                        "DataType": "Html",
                                                        "Url": (
                                                            "https://www.ris.bka.gv.at/"
                                                            "Dokumente/Bundesnormen/"
                                                            "NOR11013238/NOR11013238.html"
                                                        ),
                                                    }
                                                ]
                                            },
                                        }
                                    },
                                }
                            },
                        }
                    }
                },
                request=request,
            )

        raise httpx.ReadTimeout("timed out", request=request)


@pytest.mark.asyncio
async def test_ris_ogd_provider_returns_failed_result_when_document_fetch_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", TimeoutingRisAsyncClient)
    provider = RisOgdProvider()

    result = await provider.start_run(
        SimpleNamespace(),
        SimpleNamespace(
            acquisition_spec={
                "provider": "ris_ogd",
                "base_url": "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht",
                "applikation": "BrKons",
                "preferred_formats": ["Html", "Xml"],
                "page_size": 1,
                "max_pages": 1,
                "request_timeout_seconds": 7.0,
            }
        ),
        SimpleNamespace(run_id="run_timeout_123", scope=None),
    )

    assert result.provider == "ris_ogd"
    assert result.response_payload["captured"] == 0
    assert result.response_payload["failed"] == 1
    assert result.inline_resources == []
    assert "did not capture any resources" in (result.inline_failure_reason or "")
    assert "timed out after 7.0s" in result.response_payload["failures"][0]["error"]


# ---------------------------------------------------------------------------
# Temporal validity (#663)
#
# The RIS path acquired the validity window and then dropped it: it was written
# to `metadata.extracted_metadata.in_force_from` / `in_force_to` — a path the
# search projection never reads, under a key (`in_force_to`) that is not the
# contract vocabulary (`in_force_until`). Austrian law therefore answered
# `unknown` for a reason that had nothing to do with RIS.
#
# Shapes below are copied from live OGD responses (2026-07-19), norm
# NOR11013238 — a real repealed Verordnung.
# ---------------------------------------------------------------------------


def _brkons_ref(brkons: dict) -> dict:
    return {
        "Data": {
            "Metadaten": {
                "Technisch": {"ID": "NOR11013238", "Applikation": "BrKons"},
                "Allgemein": {"DokumentUrl": "https://www.ris.bka.gv.at/eli/test"},
                "Bundesrecht": {
                    "Titel": "Verordnung des Bundesministers",
                    "Kurztitel": "Test-Verordnung",
                    "Eli": "eli/bgbl/test",
                    "BrKons": brkons,
                },
            }
        }
    }


def test_the_ris_end_date_is_the_inclusive_last_day_in_force() -> None:
    """The boundary, measured — not the passthrough (#843).

    The test below it asserts that `2018-12-31` in comes out as `2018-12-31`; the
    input and the expectation are the same string, so it pins that the value
    SURVIVES the mapping and says nothing about what it MEANS. That is how
    `in_force_until` reached the index with no established reading at all.

    What it means, measured live 2026-09-03 against B-VG (Gesetzesnummer
    10000138) — the probe #843 named, a version's end date against its
    successor's start date:

        Art. 11  NOR40211942  1998-… 2020-01-01 -> 2024-04-30
                 NOR40261486             2024-05-01 -> (open)
        Art. 15  NOR40211946             2019-02-01 -> 2024-02-26
                 NOR40260251             2024-02-27 -> 2024-07-18

    Successor start is predecessor end **+ 1 day** in both pairs. An exclusive
    end-date would make the two dates equal. Corroborated by RIS's own
    point-in-time query: `Fassung.FassungVom=2024-04-30` returns NOR40211942, the
    version whose `Ausserkrafttretensdatum` IS 2024-04-30.

    So RIS agrees with our `in_force_until` and the provider correctly converts
    nothing. The dates here are the measured B-VG Art. 11 pair, so this test is
    tied to an observation rather than to a plausible-looking pair of strings.
    """
    superseded = _extract_metadata(
        _brkons_ref({"Inkrafttretensdatum": "2020-01-01", "Ausserkrafttretensdatum": "2024-04-30"})
    )
    successor = _extract_metadata(_brkons_ref({"Inkrafttretensdatum": "2024-05-01"}))

    assert superseded["in_force_until"] == "2024-04-30"
    assert successor["in_force_from"] == "2024-05-01"
    # The gap is the whole assertion: adjacent versions do not share a date.
    assert superseded["in_force_until"] < successor["in_force_from"]

    # And that is exactly what the consumer means by `in_force_until` —
    # legal-search/api/src/core/norm-hierarchy/in-force.ts:24-28 repeals only on
    # `asOf > until`, so the norm is in force on 2024-04-30 and repealed on
    # 2024-05-01, which is the successor's first day. No day is claimed twice and
    # no day falls between the two versions.
    assert date.fromisoformat(successor["in_force_from"]) == date.fromisoformat(
        superseded["in_force_until"]
    ) + timedelta(days=1)


def test_extract_metadata_reads_the_ris_validity_window() -> None:
    """The window RIS publishes must survive acquisition in ISO form.

    A passthrough assertion by construction — see the boundary test above for
    what the value MEANS. Both are needed: this one catches a mapping that drops
    or reformats the date, that one catches a mapping that shifts it.
    """
    meta = _extract_metadata(
        _brkons_ref(
            {
                "Inkrafttretensdatum": "1998-04-24",
                "Ausserkrafttretensdatum": "2018-12-31",
                "NovellenBeziehung": "aufgehoben durch",
                "Gesetzesnummer": "10012838",
            }
        )
    )

    assert meta["in_force_from"] == "1998-04-24"
    assert meta["in_force_until"] == "2018-12-31"
    assert meta["amendment_relation"] == "repealed_by"
    assert meta["gesetzesnummer"] == "10012838"


def test_extract_metadata_leaves_an_in_force_norm_open_ended() -> None:
    """RIS omits `Ausserkrafttretensdatum` while a norm is still in force.

    That absence is meaningful and must not be filled in — an open-ended window
    is what lets downstream logic say "in force", and a fabricated end date
    would silently expire live law.
    """
    meta = _extract_metadata(
        _brkons_ref(
            {
                "Inkrafttretensdatum": "2020-01-01",
                "NovellenBeziehung": "zuletzt geändert durch",
            }
        )
    )

    assert meta["in_force_from"] == "2020-01-01"
    assert meta["in_force_until"] is None
    assert meta["amendment_relation"] == "last_amended_by"


def test_extract_metadata_reports_unknown_dates_as_none_rather_than_guessing() -> None:
    """An unparseable date is dropped, never coerced onto a plausible value."""
    meta = _extract_metadata(
        _brkons_ref({"Inkrafttretensdatum": "irgendwann", "Ausserkrafttretensdatum": ""})
    )

    assert meta["in_force_from"] is None
    assert meta["in_force_until"] is None


def test_unrecognised_amendment_relation_is_none_not_a_plausible_guess() -> None:
    """Mirrors #661's rule for unknown Fedlex enforcement-status codes.

    A relation we have not seen must not be bent into `repealed_by`; reporting
    None keeps the temporal answer honestly `unknown`.
    """
    meta = _extract_metadata(
        _brkons_ref(
            {"Inkrafttretensdatum": "2020-01-01", "NovellenBeziehung": "wiederverlautbart durch"}
        )
    )

    assert meta["amendment_relation"] is None


def test_extract_metadata_survives_a_missing_application_block() -> None:
    """Judikatur refs carry no BrKons block; that must not raise."""
    meta = _extract_metadata(
        {
            "Data": {
                "Metadaten": {
                    "Technisch": {"ID": "JJT_123", "Applikation": "Vfgh"},
                    "Judikatur": {"Titel": "Erkenntnis"},
                }
            }
        }
    )

    assert meta["in_force_from"] is None
    assert meta["in_force_until"] is None
    assert meta["amendment_relation"] is None


# ---------------------------------------------------------------------------
# The capture guard (#631/#716)
#
# RIS promises a format out of band: the listing's `DataType` says Html/Xml/Pdf
# *before* the download URL is fetched, so `check_capture` is what holds the OGD
# endpoint to that promise. It is load-bearing here beyond the stub case, because
# `_fetch_single_document` decodes every body as text — a binary arriving where
# `Xml` was promised would be UTF-8-mangled and captured as a document.
#
# Mutation check: delete either guard block in `_fetch_single_document` and the two
# refusal tests below fail with `captured == 1`.
# ---------------------------------------------------------------------------

_REAL_NORM_HTML = (
    "<html><body><h1>Verordnung des Bundesministers</h1>"
    "<p>§ 1. Diese Verordnung gilt für ...</p>"
    "<p>§ 2. Abs. 1 Die Behörde hat ...</p>"
    "<p>§ 3. Abs. 2 Ziff. 1 In Kraft ab ...</p>"
    "</body></html>"
)


class _RisClient:
    """Serves the listing above plus one document response the test chooses."""

    document_response: tuple[int, bytes, dict[str, str]] = (
        200,
        _REAL_NORM_HTML.encode("utf-8"),
        {"content-type": "text/html; charset=utf-8"},
    )

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self) -> _RisClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    async def get(self, url: str, *, params=None):
        request = httpx.Request("GET", url, params=params)
        if url == "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht":
            return await TimeoutingRisAsyncClient().get(url, params=params)
        status, content, headers = self.document_response
        return httpx.Response(status, content=content, headers=headers, request=request)


async def _run_ris(monkeypatch: pytest.MonkeyPatch, client_cls: type[_RisClient]):
    monkeypatch.setattr(httpx, "AsyncClient", client_cls)
    return await RisOgdProvider().start_run(
        SimpleNamespace(),
        SimpleNamespace(
            acquisition_spec={
                "provider": "ris_ogd",
                "base_url": "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht",
                "applikation": "BrKons",
                "preferred_formats": ["Html"],
                "page_size": 1,
                "max_pages": 1,
            }
        ),
        SimpleNamespace(run_id="run_guard", scope=None),
    )


@pytest.mark.asyncio
async def test_a_genuine_norm_passes_both_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """The honest capture must survive: Austrian federal law cites `§` and `Abs.`."""
    result = await _run_ris(monkeypatch, _RisClient)

    assert result.response_payload["captured"] == 1
    metadata = result.inline_resources[0].metadata
    assert metadata["capture_guard"] == "passed"
    assert metadata["legal_text_evidence"]["legal_marker_count"] >= 3


@pytest.mark.asyncio
async def test_a_pdf_where_the_listing_promised_html_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the guard this body is decoded as UTF-8 text and captured as a norm."""

    class _Client(_RisClient):
        document_response = (
            200,
            b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n",
            {"content-type": "application/pdf"},
        )

    result = await _run_ris(monkeypatch, _Client)

    assert result.response_payload["captured"] == 0
    assert result.inline_resources == []
    assert "content_type_mismatch" in result.response_payload["failures"][0]["error"]


@pytest.mark.asyncio
async def test_a_navigation_shell_is_refused_rather_than_captured_as_a_norm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client(_RisClient):
        document_response = (
            200,
            b"<html><head><script>var x=1;</script></head><body>"
            b"<nav>Startseite Suche Kontakt</nav></body></html>",
            {"content-type": "text/html; charset=utf-8"},
        )

    result = await _run_ris(monkeypatch, _Client)

    assert result.response_payload["captured"] == 0
    assert "no_legal_text_markers" in result.response_payload["failures"][0]["error"]
