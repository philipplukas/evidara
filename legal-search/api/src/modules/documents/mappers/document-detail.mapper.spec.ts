import { describe, expect, it, vi } from 'vitest';
import type { WarnFn } from '../../../core/types/warn';
import type { CitationEntity, DocumentEntity, SectionEntity } from '../entities/document.entities';
import { mapDocumentToDetailView } from './document-detail.mapper';

// ─── Fixtures ───

const LAW_BODY_TEXT =
  'Die Mitglieder des Verwaltungsrates sind der Gesellschaft für den Schaden\nverantwortlich, den sie durch Verletzung ihrer Pflichten verursachen.\n\nWer die Erfüllung einer Aufgabe einem anderen Organ überträgt, haftet für\nden von diesem verursachten Schaden.';

const lawDoc: DocumentEntity = {
  document_id: 'doc_001',
  title: 'Bundesgesetz über das Obligationenrecht',
  jurisdiction: 'CH',
  document_type: 'law',
  authority_name: 'Fedlex',
  official_citation: 'SR 101',
  is_official: true,
  effective_date: '2024-01-01',
  structural_path: 'OR › Gesellschaftsrecht › Verantwortlichkeit',
  language: 'de',
  sections_count: 5,
  citations_count: 3,
  // The body as the index really holds it: a plain-text string with blank-line
  // paragraph breaks, exactly as document-intelligence's `body_text` builds it.
  // This fixture used to be `content_docling: { version: '1.0', body: [] }` — a
  // DoclingDocument shape no producer in this repo emits and the `text`-mapped
  // index cannot store. It proved the mapper handled a document that could not
  // exist, while every real document took the suppressed path.
  content: LAW_BODY_TEXT,
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
    expect(view.subtitle).toContain('Fedlex');
    expect(view.breadcrumbs).toEqual(['OR', 'Gesellschaftsrecht', 'Verantwortlichkeit']);
    expect(view.content).toBe(LAW_BODY_TEXT);
    expect(view.contentLanguage?.display).toBe('de');
    expect(view.contentLanguage?.label).toBe('Originalsprache');
  });

  it('should compose metadata rows with visibility', () => {
    const view = mapDocumentToDetailView(lawDoc, sections, citations);
    expect(view.metadata.length).toBeGreaterThan(0);
    expect(view.metadata).toContainEqual({
      label: 'Dokumenttyp',
      value: 'Gesetz',
      iconKey: 'dtype-law',
      visibility: 'default',
    });
    expect(view.metadata).toContainEqual({
      label: 'In Kraft',
      value: '01.01.2024',
      iconKey: 'meta-calendar',
      visibility: 'always',
    });
    expect(view.metadata).toContainEqual({
      label: 'Sprache',
      value: 'DE',
      iconKey: 'meta-language',
      visibility: 'default',
    });
    expect(view.metadata).toContainEqual({
      label: 'Behörde',
      value: 'Fedlex',
      iconKey: 'meta-authority',
      visibility: 'default',
    });
    expect(view.metadata).toContainEqual({
      label: 'Fundstelle',
      value: 'SR 101',
      iconKey: 'meta-citation',
      visibility: 'always',
    });
    expect(view.metadata).toContainEqual({
      label: 'Quelle',
      value: 'Offizielle Quelle',
      iconKey: 'meta-official',
      visibility: 'expanded',
    });
  });

  it('should set authority visibility to always for decisions', () => {
    const decisionDoc = { ...lawDoc, document_type: 'decision' };
    const view = mapDocumentToDetailView(decisionDoc, sections, citations);
    const authorityRow = view.metadata.find((r) => r.iconKey === 'meta-authority');
    expect(authorityRow?.visibility).toBe('always');
  });

  it('should include a non-active lifecycle status row when present', () => {
    const view = mapDocumentToDetailView(
      { ...lawDoc, lifecycle_status: 'superseded' },
      sections,
      citations,
    );
    expect(view.metadata[0]).toEqual({
      label: 'Status',
      value: 'Ersetzt',
      iconKey: 'meta-status',
      visibility: 'always',
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

  // The regression the mocked tests could not see: a document shaped like the
  // ones the index actually holds must carry its body through to the client.
  it('should emit the indexed body text as `content`', () => {
    const view = mapDocumentToDetailView(
      {
        document_id: 'doc_002',
        title: 'Entscheid',
        content: 'Erste Erwägung.\n\nZweite Erwägung.',
      },
      [],
      [],
    );
    expect(view.content).toBe('Erste Erwägung.\n\nZweite Erwägung.');
  });

  it('should not advertise an Inhalt tab for a document with no body', () => {
    const view = mapDocumentToDetailView(minimalDoc, [], []);
    expect(view.content).toBeUndefined();
    expect(view.tabs.map((t) => t.key)).not.toContain('content');
  });

  it('should treat a whitespace-only body as no body', () => {
    const view = mapDocumentToDetailView(
      { document_id: 'doc_003', title: 'Leer', content: '   \n\n  ' },
      [],
      [],
    );
    expect(view.content).toBeUndefined();
    expect(view.tabs.map((t) => t.key)).not.toContain('content');
  });

  it('should not advertise a citations tab when no references back it', () => {
    // The index says the document has 3 citations, but the citations query
    // returned none — a lagging or empty citations index. Advertising the tab
    // here yields a confident "Zitate (3)" over an empty payload (#622).
    const view = mapDocumentToDetailView(lawDoc, sections, []);
    expect(view.references).toHaveLength(0);
    expect(view.tabs.map((t) => t.key)).not.toContain('citations');
  });

  it('should advertise a citations tab when references back it', () => {
    const view = mapDocumentToDetailView(lawDoc, sections, citations);
    expect(view.tabs.map((t) => t.key)).toContain('citations');
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
    mapDocumentToDetailView(hit, [], [], 'de', warn);
    expect(warn).toHaveBeenCalledWith('unknown_document_type_detail', {
      document_id: 'doc_099',
      document_type: 'regulation',
    });
  });

  it('should warn on unknown jurisdiction', () => {
    const warn: WarnFn = vi.fn();
    const hit = { ...minimalDoc, jurisdiction: 'XX' };
    mapDocumentToDetailView(hit, [], [], 'de', warn);
    expect(warn).toHaveBeenCalledWith('unknown_jurisdiction_detail', {
      document_id: 'doc_099',
      jurisdiction: 'XX',
    });
  });

  it('should not leak raw unknown document_type codes into detail subtitles', () => {
    const view = mapDocumentToDetailView(
      { ...minimalDoc, document_type: 'regulation' },
      [],
      [],
      'de',
    );
    expect(view.subtitle).toBe('Dokument');
  });
});

describe('date rendering', () => {
  it('emits a Swiss-formatted date, not the raw ISO value', () => {
    // #761: the frontend printed `2015-12-22` in a German-language legal UI while
    // `formatSwissDate` sat unused with a passing cross-surface test over it. The
    // assertion belongs where the value is actually produced for display, or the
    // next regression passes the same way.
    const view = mapDocumentToDetailView(lawDoc, [], [], 'de');
    const dateRow = view.metadata.find((row) => row.iconKey === 'meta-calendar');

    expect(dateRow?.value).toBe('01.01.2024');
    expect(dateRow?.value).not.toContain('2024-01-01');
  });
});
