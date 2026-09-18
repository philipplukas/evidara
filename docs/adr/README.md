# Architecture Decision Records (ADRs)

Human-readable decisions for Evidara. The [MkDocs navigation](../index.md) lists a subset of these under **ADRs** — see the note below the table.

| ADR | Document |
|-----|----------|
| ADR-0001 | [Monorepo structure](0001-monorepo-structure.md) |
| ADR-0002 | [Top-level component boundaries](0002-top-level-component-boundaries.md) |
| ADR-0003 | [Storage strategy](0003-storage-strategy.md) |
| ADR-0004 | [Contract strategy](0004-contract-strategy.md) |
| ADR-0005 | [Search strategy](0005-search-strategy.md) |
| ADR-0006 | [Internal ops UI strategy](0006-internal-ops-ui-strategy.md) |
| ADR-0007 | [OpenAPI client strategy (legal-search)](0007-openapi-client-strategy-legal-search.md) |
| ADR-0008 | [Contract interaction model](0008-contract-interaction-model.md) |
| ADR-0008 (NestJS) | [NestJS conventions (legal-search API)](0008-nestjs-conventions-legal-search.md) |
| ADR-0009 | [Technology stack and language boundaries](0009-technology-stack-and-language-boundaries.md) |
| ADR-0009 (FastAPI) | [FastAPI conventions (platform-control)](0009-fastapi-conventions-platform-control.md) |
| ADR-0010 | [Document content format](0010-document-content-format.md) |
| ADR-0012 | [Layered contract governance](0012-layered-contract-governance.md) |
| ADR-0013 | [Internationalization strategy](0013-internationalization-strategy.md) |
| ADR-0014 | [Document intelligence pipeline integration](0014-document-intelligence-pipeline-integration.md) |
| ADR-0015 | [Control plane admin frontend strategy](0015-control-plane-admin-frontend-strategy.md) |
| ADR-0016 | [Cloud Run services vs jobs](0016-cloud-run-services-vs-jobs.md) |
| ADR-0020 | [API authentication](adr-0020-api-authentication.md) |
| ADR-0021 | [Wizard orchestration abstraction](adr-0021-wizard-orchestration-abstraction.md) |
| ADR-0022 | [Agentic CLI workflow control surface](adr-0022-agentic-cli-workflow-control-surface.md) (amended by ADR-0056) |
| ADR-0023 | [DSPy extraction acceleration](adr-0023-dspy-extraction-acceleration.md) |
| ADR-0024 | [Phased CI runner strategy for Evidara](adr-0024-ci-runner-strategy.md) |
| ADR-0025 | [Portal HTTP provider strategy](adr-0025-portal-http-provider-strategy.md) |
| ADR-0026 | [`authority_id` / `jurisdiction_id` naming policy](adr-0026-id-naming-policy.md) |
| ADR-0027 | [Workspace ↔ admin visual language](0027-workspace-admin-visual-language.md) |
| ADR-0028 | [Shared shell module — `@evidara/shell` path alias](0028-shared-shell-module.md) |
| ADR-0029 | [Self-hosted Hetzner runtime — retire GCP managed services](0029-self-hosted-hetzner-runtime.md) |
| ADR-0030 | [Acquisition provider enablement lifecycle](0030-acquisition-provider-enablement-lifecycle.md) |
| ADR-0031 | [Disposition of Temporal, Argilla, and Firecrawl](0031-temporal-argilla-firecrawl-disposition.md) (Accepted) |
| ADR-0032 | [Pipeline observability — Prometheus, Grafana, and a funnel that cannot lie](0032-pipeline-observability.md) |
| ADR-0033 | [Agentic legal reasoning — RAG to enter, graph to reason](0033-agentic-legal-reasoning.md) (Accepted) |
| ADR-0034 | [Generate the platform-control contract from the app](0034-generated-platform-control-contract.md) |
| ADR-0035 | [Operator-reachable blueprint enablement](0035-operator-reachable-blueprint-enablement.md) |
| ADR-0036 | [Nessie + Trino + Iceberg lakehouse for the DI canonical surfaces](0036-nessie-trino-lakehouse-for-di-surfaces.md) |
| ADR-0037 | [Binary artifacts end-to-end and a layout-aware PDF normaliser](0037-binary-artifacts-and-layout-aware-pdf.md) |
| ADR-0038 | [User identity, roles, and genuine operator attribution](0038-user-identity-and-operator-attribution.md) (Accepted) |
| ADR-0039 | [A third frontend surface — the public marketing page](0039-public-marketing-surface.md) |
| ADR-0040 | [What makes a test result trustworthy](0040-test-result-trust.md) |
| ADR-0041 | [Separate the Randtitel band geometrically, and do not adopt Docling for PDFs](0041-geometric-pdf-marginalia.md) |
| ADR-0042 | [Corpus coverage is an API, and it is a claim about the corpus — never about the law](0042-corpus-coverage-as-an-api.md) |
| ADR-0043 | [A source's scope is a measurement, not an assumption](0043-source-scope-must-be-measured.md) |
| ADR-0044 | [A pipeline transformation is disclosed where the text is read](0044-pipeline-transformations-are-disclosed.md) |
| ADR-0045 | [The admin derives its wire types from the generated contract](0045-admin-derives-wire-types-from-the-contract.md) (Accepted) |
| ADR-0046 | [A blueprint template takes operator seeds, and nothing else](0046-blueprint-templates-take-operator-seeds.md) |
| ADR-0047 | [Quarantine — the corpus holds only documents whose class we have implemented](0047-quarantine-unhandled-document-classes.md) |
| ADR-0048 | [Completeness crosses the boundary by projection, and never becomes a score](0048-completeness-crosses-the-boundary-by-projection.md) |
| ADR-0049 | [Workloads never hold the object-store root credential](0049-workloads-never-hold-the-object-store-root-credential.md) |
| ADR-0050 | [One rule, one enforcement point](0050-one-rule-one-enforcement-point.md) (Proposed) |
| ADR-0051 | [A gate that cannot fail is not a gate](0051-a-gate-that-cannot-fail-is-not-a-gate.md) (Proposed) |
| ADR-0052 | [Declared means produced](0052-declared-means-produced.md) (Proposed) |
| ADR-0053 | [Effects follow the verdict](0053-effects-follow-the-verdict.md) (Proposed) |
| ADR-0054 | [Semantic retrieval as a measured cascade](0054-semantic-retrieval-as-a-measured-cascade.md) (Proposed) |
| ADR-0055 | [GitOps with Argo CD](0055-gitops-argocd-over-imperative-apply.md) |
| ADR-0056 | [Agentic flows are visible in the panel](0056-agentic-flows-are-visible-in-the-panel.md) (amends ADR-0022) |
| ADR-0057 | [Retraction is a record, not a deletion — and never a legal claim](0057-retraction-is-a-record-not-a-deletion.md) (Proposed) |
| ADR-0058 | [A terminal outcome is recorded where someone will see it](0058-a-document-reaches-a-terminal-state-or-is-unaccounted-for.md) (Proposed) |
| ADR-0059 | [An event is a fact another component acts on; a log is an explanation for a human](0059-an-event-is-a-fact-a-log-is-an-explanation.md) (Proposed) |
| ADR-0060 | [Inspection finds what no rule was written for](0060-inspection-finds-what-no-rule-was-written-for.md) (Proposed) |
| SLI/SLO | [Definitions](sli-slo-definitions.md) |

Some filenames reuse numeric prefixes where historical numbering overlapped; treat the **title inside each file** as authoritative when in doubt.

**This table is hand-maintained, and it was eleven entries behind the directory** until
2026-09-03: ADR-0028, 0031, 0033, 0036, 0037 and 0044 through 0049 existed in `docs/adr/`
and were listed nowhere. The MkDocs navigation this file claims mirrors it still stops at
ADR-0042. Listing here is not what makes an ADR real — `scripts/check_adr_numbers.py` reads
the directory, not this table — so when the two disagree, `ls docs/adr/` wins. The gap was
an instance of [ADR-0052](0052-declared-means-produced.md) in prose: an index that omits an
entry reads as *"no such decision"*.
