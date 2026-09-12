import { describe, expect, it } from 'vitest';
import {
  CITATION_TARGETS_INDEX_PROPERTIES,
  CITATIONS_INDEX_PROPERTIES,
  citationsIndexDefinition,
  citationTargetsIndexDefinition,
} from './citation-graph-index.mapping';

type MappedField = { type: string; fields?: Record<string, { type: string }> };

describe('citation graph index mappings', () => {
  it('maps every field the projection path writes to a citation row', () => {
    // Mirrors `CitationProjection` in projections.repository.ts. A field missing
    // here gets whatever OpenSearch guesses on first write.
    for (const field of [
      'citation_id',
      'source_document_id',
      'source_section_id',
      'target_document_id',
      'target_title',
      'citation_text',
      'citation_type',
      'normalized_reference',
      'resolved',
      'resolution_status',
      'unresolved_reason',
    ]) {
      expect(CITATIONS_INDEX_PROPERTIES).toHaveProperty(field);
    }
  });

  it('maps every field the projection path writes to a citation target', () => {
    // Mirrors `CitationTargetEntry`.
    for (const field of [
      'document_id',
      'identifier_type',
      'identifier_value',
      'title',
      'document_type',
      'jurisdiction',
    ]) {
      expect(CITATION_TARGETS_INDEX_PROPERTIES).toHaveProperty(field);
    }
  });

  it('exposes the join keys via a .keyword sub-field', () => {
    // The traversal adapter filters on `<field>.keyword`, which is the one form
    // that resolves against BOTH the managed mapping and the already-live
    // `citations` index created by dynamic mapping. If these lose their
    // sub-field, every traversal query silently matches nothing.
    const joinKeys: MappedField[] = [
      CITATIONS_INDEX_PROPERTIES.normalized_reference,
      CITATIONS_INDEX_PROPERTIES.target_document_id,
      CITATIONS_INDEX_PROPERTIES.source_document_id,
      CITATIONS_INDEX_PROPERTIES.citation_type,
      CITATION_TARGETS_INDEX_PROPERTIES.identifier_type,
      CITATION_TARGETS_INDEX_PROPERTIES.identifier_value,
      CITATION_TARGETS_INDEX_PROPERTIES.document_id,
    ];
    for (const field of joinKeys) {
      expect(field.type).toBe('keyword');
      expect(field.fields?.keyword?.type).toBe('keyword');
    }
  });

  it('builds create-index bodies with settings and mappings', () => {
    for (const definition of [citationsIndexDefinition(), citationTargetsIndexDefinition()]) {
      expect(definition).toHaveProperty('settings');
      expect(definition).toHaveProperty('mappings');
      expect((definition.settings as Record<string, unknown>).number_of_replicas).toBe(0);
    }
    const withReplica = citationTargetsIndexDefinition(1);
    expect((withReplica.settings as Record<string, unknown>).number_of_replicas).toBe(1);
  });
});
