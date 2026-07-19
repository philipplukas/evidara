/**
 * Live-vs-canonical mapping drift detection for the `documents` index.
 *
 * WHY THIS EXISTS (#675)
 * ----------------------
 * `documents-index.mapping.ts` is declared the source of truth, but nothing
 * enforced that the running index actually matched it. It did not: the live
 * index was created from a hand-maintained mapping (see
 * `scripts/validate-tar89-metadata-local.sh`) that omits the `.keyword`
 * sub-fields and the projection-only ID fields. Aggregating a field that does
 * not exist is not an error in OpenSearch — it silently returns empty buckets
 * — so the facet rail was dead with every layer individually "correct".
 *
 * The dangerous part was the diagnosis, not the outage: with only a live index
 * to look at, "the sub-fields do not exist" reads as "the code asks for the
 * wrong field", and the tempting fix is to weaken the query to match the
 * drift. That fix would then break facets against any correctly-created index.
 * A drift report names the drifted side explicitly, which is what makes the
 * difference between the two diagnoses visible.
 *
 * This module is deliberately PURE — it takes two mapping property maps and
 * returns findings. `scripts/check-opensearch-mapping-drift.ts` supplies a
 * live mapping over HTTP; the integration test supplies one from a container.
 */

/** A single way in which a live index disagrees with the canonical mapping. */
export interface MappingDriftFinding {
  field: string;
  kind: 'missing-field' | 'type-mismatch' | 'missing-subfield' | 'analyzer-mismatch';
  expected: string;
  actual: string;
}

interface FieldDefinition {
  type?: string;
  analyzer?: string;
  fields?: Record<string, { type?: string }>;
  properties?: Record<string, unknown>;
}

/**
 * Compare a live index's `mappings.properties` against the canonical property
 * map and return every disagreement.
 *
 * Extra fields present live but absent from canonical are NOT reported: an
 * index legitimately acquires fields through dynamic mapping, and flagging
 * them would make the check noisy enough to be ignored — which is the failure
 * mode this is meant to replace. Only canonical expectations that the live
 * index fails to meet are drift.
 */
export function findMappingDrift(
  live: Record<string, unknown>,
  canonical: Record<string, unknown>,
): MappingDriftFinding[] {
  const findings: MappingDriftFinding[] = [];

  for (const [field, rawExpected] of Object.entries(canonical)) {
    const expected = rawExpected as FieldDefinition;
    const actual = live[field] as FieldDefinition | undefined;

    if (actual === undefined) {
      findings.push({
        field,
        kind: 'missing-field',
        expected: expected.type ?? 'object',
        actual: 'absent',
      });
      continue;
    }

    if (expected.type !== undefined && actual.type !== expected.type) {
      findings.push({
        field,
        kind: 'type-mismatch',
        expected: expected.type,
        actual: actual.type ?? 'unknown',
      });
    }

    if (expected.analyzer !== undefined && actual.analyzer !== expected.analyzer) {
      findings.push({
        field,
        kind: 'analyzer-mismatch',
        expected: expected.analyzer,
        actual: actual.analyzer ?? 'default',
      });
    }

    // The #675 case. A missing `.keyword` sub-field is invisible at query
    // time — the aggregation just returns nothing — so it has to be caught
    // structurally or not at all.
    for (const subfield of Object.keys(expected.fields ?? {})) {
      if (actual.fields?.[subfield] === undefined) {
        findings.push({
          field: `${field}.${subfield}`,
          kind: 'missing-subfield',
          expected: expected.fields?.[subfield]?.type ?? 'keyword',
          actual: 'absent',
        });
      }
    }
  }

  return findings.sort((a, b) => a.field.localeCompare(b.field));
}

/** Human-readable drift report, used by the script and by test failures. */
export function formatMappingDrift(findings: MappingDriftFinding[], indexLabel: string): string {
  if (findings.length === 0) {
    return `No drift: ${indexLabel} matches the canonical documents mapping.`;
  }
  const lines = findings.map(
    (finding) =>
      `  ${finding.field}: ${finding.kind} (expected ${finding.expected}, got ${finding.actual})`,
  );
  return [
    `${findings.length} mapping drift finding(s) — ${indexLabel} disagrees with the canonical`,
    'mapping in `legal-search/api/src/core/opensearch/documents-index.mapping.ts`:',
    '',
    ...lines,
    '',
    'The canonical mapping is the contract. Fix the INDEX (recreate/reindex via',
    '`bootstrapDocumentsIndex` or `scripts/opensearch-alias-cutover.ts`) — do NOT',
    'weaken queries to match the drift; that breaks every correctly-created index.',
  ].join('\n');
}
