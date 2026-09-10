"""Learned-sparse text representations for the search projection (ADR-0054).

Deliberately *sparse* and not dense, for a reason that is about this cluster and
not about model quality: a dense `knn_vector` needs `index.knn`, which is a
**static** index setting the live `documents-*` indices do not carry and cannot
gain without a reindex and an alias cutover — and its HNSW graphs live in
off-heap memory the 2Gi OpenSearch node does not have. A `rank_features` field
is an ordinary Lucene inverted index: it can be added to a live mapping, it costs
no off-heap memory, and it is the representation this hardware can actually
serve. See ADR-0054 D10.
"""

from document_intelligence.embeddings.gating import (
    Candidate,
    GateConfig,
    GateDecision,
    RefusalReason,
    gate,
    query_weight_mass,
)
from document_intelligence.embeddings.sparse import (
    SparseEncoder,
    SparseVector,
    pool_sparse_chunks,
    sanitize_features,
)

__all__ = [
    "Candidate",
    "GateConfig",
    "GateDecision",
    "RefusalReason",
    "SparseEncoder",
    "SparseVector",
    "gate",
    "pool_sparse_chunks",
    "query_weight_mass",
    "sanitize_features",
]
