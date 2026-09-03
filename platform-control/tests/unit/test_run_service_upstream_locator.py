"""`_upstream_locator` is the string document identity is derived from (#652, #806).

`document_id = stable_prefixed_id("doc", tenant, corpus, source, upstream_locator)` in
`document_intelligence/pipeline.py`, and the projection upserts on `document_id`
(`legal-search/api/src/modules/projections/opensearch.adapter.ts` `upsertProjection`).
So this one helper decides both whether two acquisitions of the same law converge on one
document and whether two different documents collide onto one — and it had no test at all
until #806.
"""

from __future__ import annotations

from platform_control.services.run_service import RunService

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


def test_upstream_locator_keys_on_the_stable_source_url_not_the_resolved_final_url() -> None:
    """Consolidating a Fedlex act must yield the *same* document, not another copy.

    `source_url` and `final_url` are different URIs by construction here — not a redirect
    accident — and only `source_url` identifies the act. Preferring `final_url` puts the
    consolidation date into `document_id`, so every consolidation would mint a new
    searchable copy of the same law: #652, permanently, across the federal corpus.
    """
    first = RunService._upstream_locator(
        {"source_url": FEDLEX_ELI, "final_url": FEDLEX_FILESTORE_2024}
    )
    later = RunService._upstream_locator(
        {"source_url": FEDLEX_ELI, "final_url": FEDLEX_FILESTORE_2026}
    )

    assert first == later == FEDLEX_ELI
    assert "20240303" not in first
    assert "20260101" not in later


def test_upstream_locator_falls_back_to_final_url_when_there_is_no_source_url() -> None:
    """`final_url` is still better than nothing when a provider sets only that."""
    assert (
        RunService._upstream_locator({"source_url": "", "final_url": FEDLEX_FILESTORE_2024})
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
    locator = RunService._upstream_locator({"source_url": "", "final_url": ""})

    assert locator == ""
    assert "unknown.local" not in locator


def test_upstream_locator_is_empty_when_the_artifact_carries_no_url_keys_at_all() -> None:
    assert RunService._upstream_locator({}) == ""
