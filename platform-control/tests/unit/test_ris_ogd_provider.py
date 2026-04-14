from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from platform_control.services.ris_ogd_provider import RisOgdProvider


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
