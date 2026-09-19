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

/**
 * Sections as the `sections` index really holds them: nested by `depth`, each
 * carrying the `content_preview` the mapper used to drop. The third row has a
 * whitespace-only preview, which the index does store and which must not reach
 * the client as `text: ''`.
 */
const nestedSections: SectionEntity[] = [
  {
    section_id: 'sec_100',
    document_id: 'doc_001',
    title: 'I. Allgemeine Bestimmungen',
    ordinal: 0,
    depth: 0,
    content_preview: 'Dieses Gesetz regelt die Haltung von Hunden.',
  },
  {
    section_id: 'sec_101',
    document_id: 'doc_001',
    title: '§ 1 Meldepflicht',
    ordinal: 1,
    depth: 1,
    content_preview: 'Wer einen Hund hält, meldet ihn der Gemeinde.',
  },
  {
    section_id: 'sec_102',
    document_id: 'doc_001',
    title: '§ 2 Aufgehoben',
    ordinal: 2,
    depth: 1,
    content_preview: '   ',
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

/**
 * A citation exactly as the ZH Hundegesetz's four are indexed: a well-formed
 * key, no target, and a recorded reason. Measured live 2026-09-19 (#1040).
 */
const unresolvedCitations: CitationEntity[] = [
  {
    citation_id: 'cit_doc_001_1',
    source_document_id: 'doc_001',
    citation_text: 'SR 455.1',
    citation_type: 'SR',
    normalized_reference: 'sr:455.1',
    resolved: false,
    unresolved_reason: 'no_target_in_corpus',
  },
];

/** Indexed before `unresolved_reason` existed: unresolved, cause unrecorded. */
const reasonlessCitation: CitationEntity = {
  citation_id: 'cit_doc_001_2',
  source_document_id: 'doc_001',
  citation_text: 'SR 210',
  citation_type: 'SR',
  resolved: false,
};

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

  it('should qualify a decision date as unverified in the glance strip and Details tab', () => {
    // Both surfaces read `view.metadata`, so one assertion covers both render
    // sites. `effective_date` is body-scraped for decisions and wrong on 16 of
    // 20 seeded documents (#759) — it must not read as a checked field.
    const decisionDoc = { ...lawDoc, document_type: 'decision' };
    const view = mapDocumentToDetailView(decisionDoc, sections, citations);
    expect(view.metadata).toContainEqual({
      label: 'Datum (unbestätigt)',
      value: '01.01.2024',
      iconKey: 'meta-calendar',
      visibility: 'always',
    });
    expect(view.metadata.map((row) => row.label)).not.toContain('Datum');
  });

  // #787: the frontend has no fallback. A row that arrives without a
  // `visibility` is not rendered at a lower priority — `filterByDensity`
  // drops it at compact AND default density, so the reader never sees it and
  // nothing errors. The BFF is the only place this can be guaranteed, so it
  // is guaranteed here, over every branch of `composeMetadata` and every
  // locale — not just the `lawDoc` happy path.
  it('should set visibility on every metadata row, for every doc type and locale', () => {
    const docTypes = ['law', 'decision', 'commentary', 'regulation'];
    // Every locale the BFF supports — the point of the test is that the
    // guarantee does not depend on which language the labels come out in.
    const locales = ['de', 'fr'] as const;

    // `lawDoc` + a non-active lifecycle status satisfies the condition on all 8
    // `rows.push` branches in `composeMetadata`, so the loop below covers every
    // row the mapper can emit rather than a convenient subset. If a branch is
    // added without being exercised here, this count goes stale and says so.
    const allBranches = mapDocumentToDetailView(
      { ...lawDoc, lifecycle_status: 'superseded' },
      sections,
      citations,
      'de',
    );
    expect(allBranches.metadata).toHaveLength(8);

    for (const documentType of docTypes) {
      for (const locale of locales) {
        const view = mapDocumentToDetailView(
          { ...lawDoc, document_type: documentType, lifecycle_status: 'superseded' },
          sections,
          citations,
          locale,
        );

        // 8, or 7 for a type with no localized label — that branch drops its row.
        expect(view.metadata.length).toBeGreaterThanOrEqual(7);

        for (const row of view.metadata) {
          expect(
            ['always', 'default', 'expanded'],
            `${documentType}/${locale} row "${row.label}" has visibility ${String(row.visibility)}`,
          ).toContain(row.visibility);
        }
      }
    }
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

  // The Regeste is the headnote a lawyer reads first. It was indexed, boosted
  // and highlighted by the search adapter long before it could reach the detail
  // response, so the result list carried more legal signal than the page it
  // linked to (#760).
  it('should emit the indexed regeste as prose, not as a metadata row', () => {
    const view = mapDocumentToDetailView(
      {
        document_id: 'doc_004',
        title: 'BGer 4A_123/2022',
        document_type: 'decision',
        regeste: 'Art. 754 OR; Verantwortlichkeit.\n\nDie Beweislast liegt beim Kläger.',
      },
      [],
      [],
    );
    expect(view.regeste).toBe(
      'Art. 754 OR; Verantwortlichkeit.\n\nDie Beweislast liegt beim Kläger.',
    );
    expect(view.metadata.map((row) => row.value)).not.toContain(view.regeste);
  });

  it('should trim surrounding whitespace off the regeste', () => {
    const view = mapDocumentToDetailView(
      { document_id: 'doc_005', title: 'Entscheid', regeste: '\n  Kurze Regeste.  \n' },
      [],
      [],
    );
    expect(view.regeste).toBe('Kurze Regeste.');
  });

  it('should omit a blank regeste rather than ship an empty headnote', () => {
    const view = mapDocumentToDetailView(
      { document_id: 'doc_006', title: 'Entscheid', regeste: '   \n  ' },
      [],
      [],
    );
    expect(view.regeste).toBeUndefined();
    expect('regeste' in view).toBe(false);
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

  it('should carry the target document id beside the href on a resolved citation', () => {
    // The reader navigates by `?item=<document_id>`, not by URL path, so the
    // id is what it needs. Before #1040 it had only `href`, read it as a
    // document id, and called GET /v1/documents/cit_… — a 404 on every click.
    const view = mapDocumentToDetailView(lawDoc, sections, citations);
    const item = view.references[0].items[0];
    expect(item.resolved).toBe(true);
    expect(item.targetDocumentId).toBe('doc_010');
    expect(item.unresolvedReason).toBeUndefined();
  });

  it('should compose localStructure from sections', () => {
    const view = mapDocumentToDetailView(lawDoc, sections, citations);
    expect(view.localStructure).toBeDefined();
    expect(view.localStructure!.items).toHaveLength(2);
    expect(view.localStructure!.items[0].label).toBe('Allgemeine Bestimmungen');
  });

  it('should carry section depth and text into localStructure', () => {
    // The `sections` index carries `depth` and `content_preview` on every one
    // of its 50,389 rows. `composeLocalStructure` emitted neither the text nor
    // — one hop later — the depth, so the outline arrived as a flat list of
    // labels with nothing under them (#1040).
    const view = mapDocumentToDetailView(lawDoc, nestedSections, []);
    const items = view.localStructure!.items;

    expect(items.map((i) => i.depth)).toEqual([0, 1, 1]);
    expect(items[0].text).toBe('Dieses Gesetz regelt die Haltung von Hunden.');
    expect(items[1].text).toBe('Wer einen Hund hält, meldet ihn der Gemeinde.');
  });

  it('should omit section text when the preview is blank rather than shipping an empty string', () => {
    // Same rule as `content` and `regeste`: the client cannot tell "no text"
    // from "text that is blank" once the key is present.
    const view = mapDocumentToDetailView(lawDoc, nestedSections, []);
    const blank = view.localStructure!.items[2];

    expect(blank.text).toBeUndefined();
    expect('text' in blank).toBe(false);
  });

  // ─── Unresolved citations (ADR-0052: unknown is not zero) ───
  //
  // GUARD. The rule under test is `composeReferences`'s `const resolved =
  // Boolean(cit.target_document_id)` and the two spreads it gates. Delete the
  // `resolved` key from the emitted item, or key it off `cit.resolved`
  // instead, and the two assertions below go red.

  it('should mark a citation whose target the corpus does not hold as unresolved', () => {
    const view = mapDocumentToDetailView(lawDoc, [], unresolvedCitations);
    const item = view.references[0].items[0];

    expect(item.resolved).toBe(false);
    expect(item.unresolvedReason).toBe('no_target_in_corpus');
  });

  it('should give an unresolved citation no href and no target id to follow', () => {
    // The whole defect: an unresolved row rendered identically to a
    // resolvable one, so clicking it navigated to a document that is not in
    // the corpus. A dead reference must carry nothing to follow.
    const view = mapDocumentToDetailView(lawDoc, [], unresolvedCitations);
    const item = view.references[0].items[0];

    expect(item.href).toBeUndefined();
    expect(item.targetDocumentId).toBeUndefined();
  });

  it('should still report unresolved when the index recorded no reason', () => {
    // Absent reason is a third state. The row stays unresolved; it does not
    // acquire an invented cause, and it does not silently become resolvable.
    const view = mapDocumentToDetailView(lawDoc, [], [reasonlessCitation]);
    const item = view.references[0].items[0];

    expect(item.resolved).toBe(false);
    expect(item.unresolvedReason).toBeUndefined();
    expect(item.href).toBeUndefined();
  });

  it('should trust the read-time join over the index flag', () => {
    // `DocumentsService.joinUnresolvedCitations` fills `target_document_id`
    // for edges the index wrote before their target was projected, and leaves
    // the stale `resolved: false` in place. Keying off the index flag would
    // withhold a link the corpus can serve.
    const joined = { ...unresolvedCitations[0], target_document_id: 'doc_777', resolved: false };
    const item = mapDocumentToDetailView(lawDoc, [], [joined]).references[0].items[0];

    expect(item.resolved).toBe(true);
    expect(item.href).toBe('/documents/doc_777');
    expect(item.unresolvedReason).toBeUndefined();
  });

  it('should omit optional fields when absent', () => {
    const view = mapDocumentToDetailView(minimalDoc, [], []);
    expect(view.breadcrumbs).toBeUndefined();
    expect(view.content).toBeUndefined();
    expect(view.regeste).toBeUndefined();
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
