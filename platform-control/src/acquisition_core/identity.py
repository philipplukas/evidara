"""Document identity — decided once, here (#652, #806, #850).

``document_id`` is derived from the bundle manifest's ``upstream_locator``:

    document_id = stable_prefixed_id("doc", tenant, corpus, source, upstream_locator)

(``document_intelligence/pipeline.py`` ``_document_identity_key``), and the search
projection upserts on ``document_id``
(``legal-search/api/src/modules/projections/opensearch.adapter.ts``
``upsertProjection``). So the string this module returns decides two things at once:

* whether two acquisitions of the **same law** converge on one document — or
  accumulate as separate searchable copies (#652, #806);
* whether two **different** laws collide onto one document and silently overwrite
  each other.

**Identity is a per-provider decision, not a global URL preference (#850).**

The rule used to be a single global ``source_url or final_url``, re-derived in two
services. That order is correct for the SPARQL providers and *wrong* for
``lexfind_api``, and no global order can be right for both:

* ``fedlex_sparql`` — ``source_url`` is the act-level ELI and is stable;
  ``final_url`` is the filestore URL, whose path **embeds the consolidation date**.
* ``eur_lex_sparql`` — ``source_url`` is the work/ELI URI and is stable;
  ``final_url`` is the manifestation URL, one per expression.
* ``lexfind_api`` — ``source_url`` is the canton's own page, whose path **embeds the
  version dates**; ``/tol/{id}/{lang}`` is the stable one.

Preferring ``final_url`` globally would mint a new ``document_id`` at every Fedlex
consolidation; preferring ``source_url`` globally mints a new one at every LexFind
version. Both are the #652 duplicate mechanism.

So a provider that knows which of its URIs identifies *the law* **states it**, by
setting :attr:`acquisition_core.providers.ProviderResource.identity_locator`. That
value travels into the raw artifact's metadata under :data:`IDENTITY_LOCATOR_KEY`
(``acquisition_core.normalization``) and wins here. The URL-preference chain remains
only as the fallback for providers that declare nothing.

Consumers must call :func:`upstream_locator` rather than re-deriving the rule. Two
copies of an identity rule is how #965 happened: the easier path becomes the real
policy, and it is usually the weaker one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Key under which a provider-declared identity locator travels in raw artifact
#: metadata. Written by ``acquisition_core.normalization.ArtifactPipeline.normalize``.
IDENTITY_LOCATOR_KEY = "identity_locator"


def upstream_locator(artifact_metadata: Mapping[str, Any] | None) -> str:
    """Return the locator ``document_id`` is derived from, for one raw artifact.

    Resolution order:

    1. ``identity_locator`` — the provider's own statement of what identifies the
       law. Authoritative when present; no URL heuristic may override it.
    2. ``source_url`` then ``final_url`` — the inline-acquisition shape written by
       ``ArtifactPipeline.normalize``. This is the historical global rule, kept as
       the fallback for providers that declare nothing. It is right for the SPARQL
       providers and was wrong for ``lexfind_api``, which now declares (#850).
    3. ``url``, then ``metadata.sourceURL`` / ``metadata.url`` — the Firecrawl
       webhook shape, whose artifact metadata *is* the provider's page payload and
       carries none of the keys above.

    Returns ``""`` when the artifact carries no locator at all. This must not become
    a shared placeholder: every locator-less artifact of a source would then derive
    the *same* ``document_id`` and silently overwrite itself in the index (the
    ``https://unknown.local/resource`` defect). Empty defers to
    ``_document_identity_key``'s per-artifact fallback — ``upstream_locator`` is
    neither required nor constrained in ``artifact-bundle-manifest.schema.json``.
    """
    metadata = artifact_metadata or {}
    nested = metadata.get("metadata")
    if not isinstance(nested, Mapping):
        nested = {}
    return str(
        metadata.get(IDENTITY_LOCATOR_KEY)
        or metadata.get("source_url")
        or metadata.get("final_url")
        or metadata.get("url")
        or nested.get("sourceURL")
        or nested.get("url")
        or ""
    )
