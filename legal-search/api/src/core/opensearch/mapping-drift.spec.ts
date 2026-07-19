import { describe, expect, it } from 'vitest';
import { DOCUMENTS_INDEX_PROPERTIES } from './documents-index.mapping';
import { findMappingDrift, formatMappingDrift } from './mapping-drift';

describe('findMappingDrift', () => {
  it('reports no drift when the live mapping is the canonical one', () => {
    const canonical = DOCUMENTS_INDEX_PROPERTIES as unknown as Record<string, unknown>;
    expect(findMappingDrift(structuredClone(canonical), canonical)).toEqual([]);
  });

  it('ignores extra live fields — dynamic mapping legitimately adds them', () => {
    const canonical = { title: { type: 'keyword' } };
    const live = { title: { type: 'keyword' }, some_dynamic_field: { type: 'text' } };
    expect(findMappingDrift(live, canonical)).toEqual([]);
  });

  it('detects a field the live index never declared', () => {
    // The `authority_ids` case: the drifted creation mapping omits it, so it is
    // absent (or dynamic-mapped) rather than the declared `keyword`.
    const drift = findMappingDrift({}, { authority_ids: { type: 'keyword' } });
    expect(drift).toEqual([
      { field: 'authority_ids', kind: 'missing-field', expected: 'keyword', actual: 'absent' },
    ]);
  });

  it('detects a dynamic-mapped `text` where canonical declares `keyword`', () => {
    const drift = findMappingDrift(
      { authority_ids: { type: 'text', fields: { keyword: { type: 'keyword' } } } },
      { authority_ids: { type: 'keyword', fields: { keyword: { type: 'keyword' } } } },
    );
    expect(drift).toEqual([
      { field: 'authority_ids', kind: 'type-mismatch', expected: 'keyword', actual: 'text' },
    ]);
  });

  it('detects a missing analyzer — the tfvars-created index declares no mapping at all', () => {
    const drift = findMappingDrift(
      { content: { type: 'text' } },
      { content: { type: 'text', analyzer: 'legal_text' } },
    );
    expect(drift).toEqual([
      { field: 'content', kind: 'analyzer-mismatch', expected: 'legal_text', actual: 'default' },
    ]);
  });

  // ── THE #675 CASE ──

  it('detects the exact drift that killed the facet rail: bare keyword facets', () => {
    // The live documents index as created by the drifted shell script: the
    // facet fields exist and are the right type, but carry no `.keyword`
    // sub-field. Nothing errors at query time — the aggregation just returns
    // empty buckets — so this is only catchable structurally.
    const live = {
      jurisdiction: { type: 'keyword' },
      document_type: { type: 'keyword' },
      language: { type: 'keyword' },
    };
    const canonical = {
      jurisdiction: { type: 'keyword', fields: { keyword: { type: 'keyword' } } },
      document_type: { type: 'keyword', fields: { keyword: { type: 'keyword' } } },
      language: { type: 'keyword', fields: { keyword: { type: 'keyword' } } },
    };

    const drift = findMappingDrift(live, canonical);

    expect(drift.map((finding) => finding.field)).toEqual([
      'document_type.keyword',
      'jurisdiction.keyword',
      'language.keyword',
    ]);
    expect(drift.every((finding) => finding.kind === 'missing-subfield')).toBe(true);
  });

  it('names the index as the drifted side, not the query', () => {
    // The report has to push toward "fix the index", because the tempting and
    // wrong reading of this drift is "the code aggregates on the wrong field".
    const report = formatMappingDrift(
      findMappingDrift(
        { jurisdiction: { type: 'keyword' } },
        {
          jurisdiction: { type: 'keyword', fields: { keyword: { type: 'keyword' } } },
        },
      ),
      'documents-read',
    );
    expect(report).toContain('jurisdiction.keyword: missing-subfield');
    expect(report).toContain('Fix the INDEX');
    expect(report).toContain('do NOT');
  });

  it('says so plainly when there is no drift', () => {
    expect(formatMappingDrift([], 'documents-read')).toContain('No drift');
  });
});
