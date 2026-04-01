import { describe, expect, it, vi } from 'vitest';
import type { WarnFn } from '../../../core/types/warn';
import type { CitationEntity, DocumentEntity, SectionEntity } from '../entities/document.entities';
import { mapDocumentToDetailView } from './document-detail.mapper';

// ─── Fixtures ───

const lawDoc: DocumentEntity = {
  document_id: 'doc_001',
  title: 'Bundesgesetz über das Obligationenrecht',
  jurisdiction: 'CH',
  document_type: 'law',
  effective_date: '2024-01-01',
  structural_path: 'OR › Gesellschaftsrecht › Verantwortlichkeit',
  language: 'de',
  sections_count: 5,
  citations_count: 3,
  content_docling: { version: '1.0', body: [] },
};

const sections: SectionEntity[] = [
  {
    section_id: 'sec_001',
    document_id: 'doc_001',
    title: 'Allgemeine Bestimmungen',
    ordinal: 0,
    depth: 0,
  },
  {
    section_id: 'sec_002',
    document_id: 'doc_001',
    title: 'Einzelne Vertragsverhältnisse',
    ordinal: 1,
    depth: 0,
  },
];

const citations: CitationEntity[] = [
  {
    citation_id: 'cit_001',
    source_document_id: 'doc_001',
    target_document_id: 'doc_010',
    target_title: 'BGE 144 III 264',
    citation_text: 'Art. 716a Abs. 1 OR',
    citation_type: 'statute_reference',
    resolved: true,
  },
];

const minimalDoc: DocumentEntity = {
  document_id: 'doc_099',
  title: 'Unknown',
};

// ─── Main mapper ───

describe('mapDocumentToDetailView', () => {
  it('should produce a complete detail view for a law doc', () => {
    const view = mapDocumentToDetailView(lawDoc, sections, citations);

    expect(view.id).toBe('doc_001');
    expect(view.type).toBe('law');
    expect(view.title).toBe('Bundesgesetz über das Obligationenrecht');
    expect(view.subtitle).toContain('Schweiz');
    expect(view.breadcrumbs).toEqual(['OR', 'Gesellschaftsrecht', 'Verantwortlichkeit']);
    expect(view.content).toEqual({ version: '1.0', body: [] });
    expect(view.contentLanguage?.display).toBe('de');
  });

  it('should compose metadata rows', () => {
    const view = mapDocumentToDetailView(lawDoc, sections, citations);
    expect(view.metadata.length).toBeGreaterThan(0);
    expect(view.metadata).toContainEqual({
      label: 'In Kraft',
      value: '2024-01-01',
    });
  });

  it('should compose tabs from counts', () => {
    const view = mapDocumentToDetailView(lawDoc, sections, citations);
    const tabKeys = view.tabs.map((t) => t.key);
    expect(tabKeys).toContain('content');
    expect(tabKeys).toContain('sections');
    expect(tabKeys).toContain('citations');
    expect(tabKeys).toContain('details');
  });

  it('should compose references from citations', () => {
    const view = mapDocumentToDetailView(lawDoc, sections, citations);
    expect(view.references).toHaveLength(1);
    expect(view.references[0].label).toBe('statute_reference');
    expect(view.references[0].items[0].title).toBe('BGE 144 III 264');
    expect(view.references[0].items[0].href).toBe('/documents/doc_010');
  });

  it('should compose localStructure from sections', () => {
    const view = mapDocumentToDetailView(lawDoc, sections, citations);
    expect(view.localStructure).toBeDefined();
    expect(view.localStructure!.items).toHaveLength(2);
    expect(view.localStructure!.items[0].label).toBe('Allgemeine Bestimmungen');
  });

  it('should omit optional fields when absent', () => {
    const view = mapDocumentToDetailView(minimalDoc, [], []);
    expect(view.breadcrumbs).toBeUndefined();
    expect(view.content).toBeUndefined();
    expect(view.contentLanguage).toBeUndefined();
    expect(view.localStructure).toBeUndefined();
  });

  it('should always return arrays per ADR-0011', () => {
    const view = mapDocumentToDetailView(minimalDoc, [], []);
    expect(Array.isArray(view.metadata)).toBe(true);
    expect(Array.isArray(view.tabs)).toBe(true);
    expect(Array.isArray(view.relatedGroups)).toBe(true);
    expect(Array.isArray(view.references)).toBe(true);
    expect(Array.isArray(view.annotations)).toBe(true);
  });

  it('should warn on unknown document_type', () => {
    const warn: WarnFn = vi.fn();
    const hit = { ...minimalDoc, document_type: 'regulation' };
    mapDocumentToDetailView(hit, [], [], warn);
    expect(warn).toHaveBeenCalledWith('unknown_document_type_detail', {
      document_id: 'doc_099',
      document_type: 'regulation',
    });
  });

  it('should warn on unknown jurisdiction', () => {
    const warn: WarnFn = vi.fn();
    const hit = { ...minimalDoc, jurisdiction: 'XX' };
    mapDocumentToDetailView(hit, [], [], warn);
    expect(warn).toHaveBeenCalledWith('unknown_jurisdiction_detail', {
      document_id: 'doc_099',
      jurisdiction: 'XX',
    });
  });
});
