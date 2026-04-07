"""Pipeline policy resolution.

Maps (source_system, document_class, jurisdiction) tuples to policy sets
that control ingestion, parsing, NLP, and serving behaviour.
"""

from document_intelligence.policy.resolver import PolicyResolver, PolicySet

__all__ = ["PolicyResolver", "PolicySet"]
