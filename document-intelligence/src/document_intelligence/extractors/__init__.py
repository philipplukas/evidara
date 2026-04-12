"""DSPy-backed extraction modules for AI-accelerated metadata enrichment.

Modules:
    dspy_modules     — TitleExtractor, SourceFamilyClassifier, CommentaryExtractor
    dspy_metadata_extractor — MetadataExtractor protocol implementation
    profile_config   — Per-step toggle configuration
    metadata         — MetadataExtractionCandidate and MetadataExtractor protocol

The ``llm`` optional dependency group must be installed for DSPy modules
to be importable at runtime. The rest of the pipeline remains deterministic.
See ADR-0023 for design decisions.
"""
