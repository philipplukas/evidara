from __future__ import annotations

from types import SimpleNamespace

from platform_control.services.legifrance_provider import LegifranceProvider


def test_legifrance_plan_honors_configured_max_articles() -> None:
    provider = LegifranceProvider()
    source_version = SimpleNamespace(
        acquisition_spec={
            "provider": "legifrance",
            "code_ids": ["LEGITEXT000006070721", "LEGITEXT000006070719"],
            "max_articles": 7,
        }
    )

    plan = provider.plan(SimpleNamespace(), source_version)

    assert plan.provider == "legifrance"
    assert plan.mode == "piste_api_code_articles"
    assert plan.seed_urls == [
        "https://www.legifrance.gouv.fr/codes/texte_lc/LEGITEXT000006070721",
        "https://www.legifrance.gouv.fr/codes/texte_lc/LEGITEXT000006070719",
    ]
    assert plan.estimated_request_count == 14
