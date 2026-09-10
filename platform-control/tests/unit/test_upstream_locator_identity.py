"""`upstream_locator` is the string document identity is derived from (#652, #806, #850).

`document_id = stable_prefixed_id("doc", tenant, corpus, source, upstream_locator)` in
`document_intelligence/pipeline.py`, and the projection upserts on `document_id`
(`legal-search/api/src/modules/projections/opensearch.adapter.ts` `upsertProjection`).
So this one helper decides both whether two acquisitions of the same law converge on one
document and whether two different documents collide onto one — and it had no test at all
until #806.

This file previously tested `RunService._upstream_locator`. That method is gone: the rule
now lives in one place, `acquisition_core.identity.upstream_locator`, called by both
`RunService` and `FirecrawlWebhookService` (#850, and the #965 lesson about a rule
enforced in two clients).
"""

from __future__ import annotations

import inspect

from acquisition_core.identity import IDENTITY_LOCATOR_KEY, upstream_locator
from acquisition_core.normalization import ArtifactPipeline
from acquisition_core.providers import ProviderResource
from platform_control.services import firecrawl_webhook_service, run_service

# Real `fedlex_sparql` shapes. `source_url` is the act-level ELI (`work_uri`);
# `final_url` is the filestore manifestation built by `_filestore_html_url`, whose path
# embeds the consolidation date.
FEDLEX_ELI = "https://fedlex.data.admin.ch/eli/cc/1999/404"
FEDLEX_FILESTORE_2024 = (
    "https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/1999/404/"
    "20240303/de/html/fedlex-data-admin-ch-eli-cc-1999-404-20240303-de-html.html"
)
FEDLEX_FILESTORE_2026 = (
    "https://www.fedlex.admin.ch/filestore/fedlex.data.admin.ch/eli/cc/1999/404/"
    "20260101/de/html/fedlex-data-admin-ch-eli-cc-1999-404-20260101-de-html.html"
)

# Real `lexfind_api` shapes, from `tests/fixtures/lexfind/search-zh-554.json`. The
# canton page — which this provider sets as `source_url`, because provenance must point
# at the canton and not at the mirror — encodes enactment and in-force dates in its path.
LEXFIND_TOL = "https://www.lexfind.ch/tol/22888/de"
LEXFIND_CANTON_V1 = (
    "https://www.zh.ch/de/politik-staat/gesetze-beschluesse/gesetzessammlung/zhlex-ls/"
    "erlass-554_51-2009_11_25-2010_01_01-129.html"
)
LEXFIND_CANTON_V2 = (
    "https://www.zh.ch/de/politik-staat/gesetze-beschluesse/gesetzessammlung/zhlex-ls/"
    "erlass-554_51-2009_11_25-2025_06_01-142.html"
)


# --------------------------------------------------------------------------
# The fallback chain — unchanged behaviour for providers that declare nothing
# --------------------------------------------------------------------------


def test_upstream_locator_keys_on_the_stable_source_url_not_the_resolved_final_url() -> None:
    """Consolidating a Fedlex act must yield the *same* document, not another copy.

    `source_url` and `final_url` are different URIs by construction here — not a redirect
    accident — and only `source_url` identifies the act. Preferring `final_url` puts the
    consolidation date into `document_id`, so every consolidation would mint a new
    searchable copy of the same law: #652, permanently, across the federal corpus.
    """
    first = upstream_locator({"source_url": FEDLEX_ELI, "final_url": FEDLEX_FILESTORE_2024})
    later = upstream_locator({"source_url": FEDLEX_ELI, "final_url": FEDLEX_FILESTORE_2026})

    assert first == later == FEDLEX_ELI
    assert "20240303" not in first
    assert "20260101" not in later


def test_upstream_locator_falls_back_to_final_url_when_there_is_no_source_url() -> None:
    """`final_url` is still better than nothing when a provider sets only that."""
    assert (
        upstream_locator({"source_url": "", "final_url": FEDLEX_FILESTORE_2024})
        == FEDLEX_FILESTORE_2024
    )


def test_upstream_locator_does_not_collapse_locatorless_artifacts_onto_one_id() -> None:
    """A source with no URL must not hand every artifact the same locator.

    `cassette_provider.py` can emit empty `source_url`/`final_url`. The shared
    `https://unknown.local/resource` placeholder made every such artifact derive one
    `document_id`, and the projection upsert then silently overwrote each document with
    the next. Empty defers to `_document_identity_key`'s per-artifact fallback
    (`upstream_locator` is not a required manifest field).
    """
    locator = upstream_locator({"source_url": "", "final_url": ""})

    assert locator == ""
    assert "unknown.local" not in locator


def test_upstream_locator_is_empty_when_the_artifact_carries_no_url_keys_at_all() -> None:
    assert upstream_locator({}) == ""
    assert upstream_locator(None) == ""


def test_upstream_locator_reads_the_firecrawl_page_shape() -> None:
    """Firecrawl artifact metadata IS the page payload — no `source_url` key at all.

    The webhook service used to carry its own copy of the identity rule for exactly this
    reason. Folding it in must not change what a Firecrawl artifact resolves to.
    """
    assert upstream_locator({"url": "https://example.gov/act-1"}) == "https://example.gov/act-1"
    assert (
        upstream_locator({"metadata": {"sourceURL": "https://example.gov/act-2"}})
        == "https://example.gov/act-2"
    )
    assert (
        upstream_locator({"metadata": {"url": "https://example.gov/act-3"}})
        == "https://example.gov/act-3"
    )
    # A non-mapping `metadata` must not raise — a provider payload is untrusted input.
    assert upstream_locator({"metadata": "not-a-dict"}) == ""


# --------------------------------------------------------------------------
# The provider-stated locator — #850
# --------------------------------------------------------------------------


def test_declared_identity_locator_beats_the_url_preference_order() -> None:
    """The whole point of #850: `source_url` is NOT globally the identity.

    A LexFind artifact carries a version-specific `source_url` and a stable
    `identity_locator`. Under the old global rule the two versions below resolve to two
    different locators — two `document_id`s — for one law. Under the declared rule they
    converge.
    """
    first = upstream_locator(
        {
            IDENTITY_LOCATOR_KEY: LEXFIND_TOL,
            "source_url": LEXFIND_CANTON_V1,
            "final_url": LEXFIND_TOL,
        }
    )
    later = upstream_locator(
        {
            IDENTITY_LOCATOR_KEY: LEXFIND_TOL,
            "source_url": LEXFIND_CANTON_V2,
            "final_url": LEXFIND_TOL,
        }
    )

    assert first == later == LEXFIND_TOL
    # The distinguishing assertion: the two `source_url`s genuinely differ, so a
    # `source_url`-first implementation would NOT satisfy the equality above.
    assert LEXFIND_CANTON_V1 != LEXFIND_CANTON_V2
    assert upstream_locator({"source_url": LEXFIND_CANTON_V1}) != upstream_locator(
        {"source_url": LEXFIND_CANTON_V2}
    )


def test_declared_identity_locator_wins_even_when_it_is_neither_url() -> None:
    """No URL heuristic may override an explicit provider statement."""
    assert (
        upstream_locator(
            {
                IDENTITY_LOCATOR_KEY: "urn:law:zh:554.51",
                "source_url": LEXFIND_CANTON_V1,
                "final_url": LEXFIND_TOL,
            }
        )
        == "urn:law:zh:554.51"
    )


def test_absent_identity_locator_is_not_a_claim_that_there_is_none() -> None:
    """Silence falls through to the URL order; it does not zero the locator."""
    assert upstream_locator({"source_url": FEDLEX_ELI}) == FEDLEX_ELI
    assert upstream_locator({IDENTITY_LOCATOR_KEY: "", "source_url": FEDLEX_ELI}) == FEDLEX_ELI


# --------------------------------------------------------------------------
# The declaration has to survive normalization to matter
# --------------------------------------------------------------------------


def test_normalize_carries_a_declared_locator_into_raw_artifact_metadata() -> None:
    """A field with no producer is worse than no field. This is the producer."""
    pairs = ArtifactPipeline().normalize(
        run_id="run_x",
        resources=[
            ProviderResource(
                source_url=LEXFIND_CANTON_V1,
                final_url=LEXFIND_TOL,
                identity_locator=LEXFIND_TOL,
                content_type="application/pdf",
                body_bytes=b"%PDF-1.7\n%%EOF\n",
            )
        ],
    )
    raw_artifact, _ = pairs[0]

    assert raw_artifact.metadata[IDENTITY_LOCATOR_KEY] == LEXFIND_TOL
    assert upstream_locator(raw_artifact.metadata) == LEXFIND_TOL


def test_normalize_omits_the_key_when_the_provider_declared_nothing() -> None:
    """Present-but-empty would read as 'this provider says there is no identity'."""
    pairs = ArtifactPipeline().normalize(
        run_id="run_x",
        resources=[
            ProviderResource(
                source_url=FEDLEX_ELI,
                final_url=FEDLEX_FILESTORE_2024,
                content_type="text/html",
                body="<html>Art. 1</html>",
            )
        ],
    )
    raw_artifact, _ = pairs[0]

    assert IDENTITY_LOCATOR_KEY not in raw_artifact.metadata
    assert upstream_locator(raw_artifact.metadata) == FEDLEX_ELI


# --------------------------------------------------------------------------
# One rule, one place
# --------------------------------------------------------------------------


def test_no_service_carries_its_own_copy_of_the_identity_rule() -> None:
    """#965's lesson: a rule enforced in two clients becomes two different rules.

    `RunService` and `FirecrawlWebhookService` both used to define `_upstream_locator`,
    with different fallback chains. Re-introducing either private copy — or any other
    hand-rolled `source_url or final_url` in these two services — fails here.
    """
    for module in (run_service, firecrawl_webhook_service):
        source = inspect.getsource(module)
        assert "def _upstream_locator" not in source, (
            f"{module.__name__} re-declared the identity rule; call "
            "acquisition_core.identity.upstream_locator instead"
        )
        assert 'get("source_url") or' not in source, (
            f"{module.__name__} re-derives the URL preference order; it belongs in "
            "acquisition_core.identity only"
        )
