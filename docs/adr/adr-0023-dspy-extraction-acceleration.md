# ADR-0023: DSPy Extraction Acceleration in Document Intelligence

## Status

Accepted

## Date

2026-04-12

## Context

The document-intelligence pipeline currently extracts metadata (titles, document types, citations) using deterministic rules: HTML heading extraction, XML field mapping, regex citation patterns, and optional spaCy NLP. This works well for structured sources (e.g. RIS XML) but produces sparse or placeholder metadata for HTML-only legal documents, reducing user trust in search results and detail views (TAR-89).

Scaling to five countries and commentary source families (M7/M8) will encounter increasingly diverse document formats where rule-based extraction cannot keep pace. We need AI-accelerated extraction that:

- Improves title, type, and metadata quality for HTML sources
- Classifies source families (law / decision / commentary / admin guidance) reliably
- Extracts commentary-specific structure (passages, referenced provisions)
- Remains optional and toggleable per extraction step
- Has measurable quality and bounded cost

The pipeline already declares `dspy>=2.5.0`, `google-cloud-aiplatform>=1.60.0`, and `openai>=1.30.0` as optional `[llm]` dependencies. A `MetadataExtractor` protocol and `enable_llm_extractor` flag exist in `ProcessingPipeline` but have no real implementation wired in the runtime path.

ADR-0022 scopes DSPy usage in `evidara-cli` to "bounded proposal or evaluation tasks with explicit inputs, outputs, and measurable quality signals." This ADR extends that principle to the DI pipeline.

## Decision

### DSPy as the extraction framework

- Use **DSPy** for all LLM-backed extraction modules in document-intelligence.
- DSPy modules are **typed functions** with explicit input/output signatures, not free-form prompt chains. This enables structured evaluation, caching, and deterministic fallback.
- Each module is a standalone class under `document_intelligence/extractors/` with a golden-fixture test suite.

### LLM provider strategy

- **Primary:** Vertex AI (Gemini) — same GCP project as runtime, no additional credentials.
- **Bootstrap/fallback:** OpenAI — for rapid prototyping and when Vertex quotas are exhausted.
- Provider selection is a runtime configuration parameter, not a code branch.

### Module inventory (M6 scope)

| Module | Input | Output | Quality target |
|--------|-------|--------|----------------|
| `TitleExtractor` | Document body + metadata hints | Extracted title + confidence | ≥90% correct on CH golden fixtures |
| `SourceFamilyClassifier` | Document body + source defaults | `law` / `decision` / `commentary` / `admin_guidance` | Correct on 20-doc eval set |
| `CommentaryExtractor` | Document body | Passages + referenced provisions | Extracts from ≥5 known commentary documents |

### Integration model

- Modules plug into `ProcessingPipeline` via the existing `MetadataExtractor` protocol.
- `ProcessingPipeline.__init__` accepts an optional `llm_metadata_extractor` — the runtime wiring in `build_processing_pipeline()` instantiates a real DSPy-backed extractor when `DI_ENABLE_LLM_EXTRACTOR=true`.
- **Per-step toggles:** Extend `RuntimeSettings` (or profile config) so individual extraction steps can be enabled/disabled independently (e.g. titles on, commentary off).

### Quality and cost guardrails

- Each module has a **confidence threshold** (default 0.7). Below-threshold results fall back to deterministic extraction.
- **Cost baseline:** Measure and document per-document cost and p95 latency before enabling in any non-dev environment.
- **DSPy assertions:** Map to golden-fixture test expectations — a module that degrades below the quality target fails CI.
- **Caching:** DSPy's built-in caching layer is enabled by default to avoid redundant LLM calls during development and re-runs.

### Boundaries

- DSPy modules are **never** in the critical path unless explicitly enabled via configuration.
- No DSPy usage outside `document_intelligence/extractors/` — the rest of the pipeline remains deterministic.
- LLM calls must be **idempotent** for the same input document; side effects (state mutations, external writes) are forbidden inside extractors.

## Consequences

### Positive

- Metadata quality improves immediately for HTML-dominant sources without per-source rule authoring.
- Golden-fixture tests enforce quality regression gates in CI.
- Commentary extraction unlocks M7 source families without manual structure templates.
- Provider flexibility avoids vendor lock-in.

### Negative

- LLM cost is per-document; must be monitored and budgeted per environment.
- Latency increases for LLM-enabled steps (mitigated by caching and async batching).
- Two extraction paths (deterministic + DSPy) must be maintained and tested.

### Neutral

- `[llm]` dependency group remains optional; CI and non-LLM deployments are unaffected.
- Profile/config surface grows but follows existing `RuntimeSettings` pattern.

## Alternatives Considered

### Raw LLM API calls (no framework)

Rejected. Unstructured prompts are harder to test, version, and evaluate. DSPy's typed signatures, assertions, and caching provide immediate structure that raw calls require building from scratch.

### LangChain

Rejected. Heavier abstraction layer with runtime overhead and opinions about chain composition that do not align with the pipeline's batch-oriented, per-document processing model. DSPy's module pattern maps more naturally to extraction functions.

### Manual prompt engineering per source family

Rejected. Does not scale to five countries with diverse document formats. Each new source family would require bespoke prompt maintenance. DSPy's optimizers can adapt modules to new distributions with evaluation data rather than manual prompt tuning.

### spaCy-only expansion

Rejected for metadata extraction (titles, types, commentary). spaCy excels at NER and sentence segmentation but cannot reliably extract semantic document structure or classify source families from diverse HTML.

## References

- `document-intelligence/src/document_intelligence/extractors/metadata.py` — `MetadataExtractor` protocol
- `document-intelligence/src/document_intelligence/pipeline.py` — `ProcessingPipeline` integration points
- `document-intelligence/pyproject.toml` — `[llm]` optional dependency group
- `docs/adr/adr-0022-agentic-cli-workflow-control-surface.md` — DSPy scope rule for CLI
- `docs/adr/0014-document-intelligence-pipeline-integration.md` — pipeline architecture
- `docs/runbooks/metadata-quality-plan-status.md` — TAR-89 acceptance criteria
- Linear: TAR-141 (DSPy spike), TAR-142 (this ADR), TAR-143 (commentary inventory)
