/**
 * Render the canonical documents-index definition as JSON text, so producers
 * that cannot import TypeScript can apply the exact same mapping (#675).
 *
 * `scripts/validate-tar89-metadata-local.sh` runs inside a bare alpine
 * container with only bash/curl/jq. It used to carry a hand-maintained copy of
 * the mapping, which drifted: no `.keyword` sub-fields, and neither
 * `jurisdiction_ids` nor `authority_ids` declared at all. Documents written to
 * that index got those two fields dynamic-mapped as `text` — or, if no document
 * carrying them was ever indexed, not mapped at all. The dead facet rail and
 * the "`authority_ids` does not exist" finding are both that one drift.
 *
 * The generated JSON is committed at `scripts/opensearch/documents-index.mapping.json`
 * (repo root `scripts/` is the only directory mounted into the container) and
 * drift-gated by `documents-index.mapping-json.spec.ts`, so a second
 * hand-maintained copy cannot re-emerge. Same generate-and-gate pattern that
 * AGENTS.md rule 4 and ADR-0034 apply to the platform-control OpenAPI contract.
 */
import { documentsIndexDefinition } from './documents-index.mapping';

const GENERATED_BANNER =
  'GENERATED FILE — do not edit. Source of truth: ' +
  'legal-search/api/src/core/opensearch/documents-index.mapping.ts. ' +
  'Regenerate with `cd legal-search/api && npm run mapping:generate`.';

/** Exact text of the committed JSON artifact, including trailing newline. */
export function renderDocumentsIndexMappingJson(): string {
  return `${JSON.stringify({ $comment: GENERATED_BANNER, ...documentsIndexDefinition() }, null, 2)}\n`;
}
