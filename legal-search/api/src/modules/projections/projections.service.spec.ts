import { describe, expect, it, vi } from 'vitest';
import type { DocumentIntelligenceClient } from '../../lib/document-intelligence/document-intelligence.client';
import type {
  DocumentProcessedEventDto,
  DocumentWithdrawnEventDto,
} from './dto/projection-events.dto';
import type { ProjectionRepository } from './projections.repository';
import { ProjectionsService } from './projections.service';

function createRepositoryMock(): ProjectionRepository {
  return {
    hasHistoryEvent: vi.fn().mockResolvedValue(false),
    listIndexedDocuments: vi.fn().mockResolvedValue({ data: [], limit: 500 }),
    getLatestRevision: vi.fn().mockResolvedValue(null),
    upsertProjection: vi.fn().mockResolvedValue(undefined),
    deleteProjection: vi.fn().mockResolvedValue(undefined),
    bulkIndexSections: vi.fn().mockResolvedValue(undefined),
    bulkIndexCitations: vi.fn().mockResolvedValue(undefined),
    bulkIndexCitationTargets: vi.fn().mockResolvedValue(undefined),
    deleteSectionsForDocument: vi.fn().mockResolvedValue(undefined),
    deleteCitationsForDocument: vi.fn().mockResolvedValue(undefined),
    appendHistory: vi.fn().mockResolvedValue(undefined),
    queryHistory: vi.fn().mockResolvedValue({ data: [], total: 0, limit: 50, offset: 0 }),
    getHistoryStats: vi.fn().mockResolvedValue({
      totalEvents: 0,
      applied: 0,
      stale: 0,
      ignoredDuplicate: 0,
      uniqueDocuments: 0,
    }),
    resolveCitationTargets: vi.fn().mockResolvedValue(new Map()),
  };
}

function createDocumentIntelligenceMock(): DocumentIntelligenceClient {
  return {
    fetchLeanDocument: vi.fn().mockResolvedValue({}),
  };
}

const baseProcessedEvent: DocumentProcessedEventDto = {
  event_id: 'evt_1',
  event_type: 'document.processed',
  event_version: 1,
  occurred_at: '2026-04-03T10:00:00Z',
  producer: 'document-intelligence',
  payload: {
    document_id: 'doc_01jq7bhgy7g0pkj4f1d03f8f8c',
    document_revision: 2,
    processing_manifest_id: 'pm_01jq7bhgy7g0pkj4f1d03f8f8c',
    processing_version: 'v1.0.0',
    authority_id: 'auth_fedlex',
    authority_name: 'Fedlex',
    is_official: true,
    lifecycle_status: 'active',
    provenance: {
      tenant_id: 'tenant_evidara',
      corpus_id: 'ch_de',
      scope_type: 'source-version',
      source_id: 'src_01jq7bhgy7g0pkj4f1d03f8f8c',
      source_version_id: 'sv_01jq7bhgy7g0pkj4f1d03f8f8c',
      run_id: 'run_01jq7bhgy7g0pkj4f1d03f8f8c',
    },
  },
};

const baseWithdrawnEvent: DocumentWithdrawnEventDto = {
  event_id: 'evt_2',
  event_type: 'document.withdrawn',
  event_version: 1,
  occurred_at: '2026-04-03T10:05:00Z',
  producer: 'document-intelligence',
  payload: {
    document_id: 'doc_01jq7bhgy7g0pkj4f1d03f8f8c',
    document_revision: 3,
    processing_manifest_id: 'pm_01jq7chgy7g0pkj4f1d03f8f8c',
    provenance: {
      tenant_id: 'tenant_evidara',
      corpus_id: 'ch_de',
      scope_type: 'source-version',
      source_id: 'src_01jq7bhgy7g0pkj4f1d03f8f8c',
      source_version_id: 'sv_01jq7bhgy7g0pkj4f1d03f8f8c',
      run_id: 'run_01jq7bhgy7g0pkj4f1d03f8f8c',
    },
    reason_code: 'operator_withdrawn',
    reason_summary: 'manual',
    search_disposition: 'remove',
  },
};

describe('ProjectionsService', () => {
  it('applies a fresh processed event and writes history', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    const result = await service.applyDocumentProcessed(baseProcessedEvent);

    expect(result.status).toBe('applied');
    expect(repository.upsertProjection).toHaveBeenCalledTimes(1);
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });

  it('ignores duplicate events by event_id', async () => {
    const repository = createRepositoryMock();
    (repository.hasHistoryEvent as ReturnType<typeof vi.fn>).mockResolvedValue(true);
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    const result = await service.applyDocumentProcessed(baseProcessedEvent);

    expect(result.status).toBe('ignored_duplicate');
    expect(repository.upsertProjection).not.toHaveBeenCalled();
    expect(repository.appendHistory).not.toHaveBeenCalled();
  });

  it('marks stale processed events when revision regresses', async () => {
    const repository = createRepositoryMock();
    (repository.getLatestRevision as ReturnType<typeof vi.fn>).mockResolvedValue(5);
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    const event = {
      ...baseProcessedEvent,
      payload: { ...baseProcessedEvent.payload, document_revision: 4 },
    };
    const result = await service.applyDocumentProcessed(event);

    expect(result.status).toBe('stale');
    expect(repository.upsertProjection).not.toHaveBeenCalled();
    expect(repository.appendHistory).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'stale' }),
    );
  });

  it('removes projection for withdrawn event and writes history', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    const result = await service.applyDocumentWithdrawn(baseWithdrawnEvent);

    expect(result.status).toBe('applied');
    expect(repository.deleteProjection).toHaveBeenCalledWith(
      baseWithdrawnEvent.payload.document_id,
    );
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });

  it('uses lean document fields when available', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Bundesgerichtsurteil 9C_100/2025',
      language: 'de',
      metadata: {
        official_citation: 'SR 101',
        original_language: 'de',
        translation_status: 'original',
      },
      sections: [{ id: 's1' }, { id: 's2' }],
      citations: [{ id: 'c1' }],
      content_text: 'Leitsatz und Sachverhalt...',
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgerichtsurteil 9C_100/2025',
        authority_name: 'Fedlex',
        official_citation: 'SR 101',
        original_language: 'de',
        translation_status: 'original',
        is_official: true,
        sections_count: 2,
        citations_count: 1,
        language: 'de',
        lifecycle_status: 'active',
        content_preview: 'Leitsatz und Sachverhalt...',
      }),
    );
  });

  it('indexes the official headnote as `regeste` when the canonical row carries one', async () => {
    // #836. `regeste` is mapped and boosted (`regeste^2`) in the documents index and
    // rendered on the detail page (#830/#760), but until DI promoted
    // `metadata.regeste` the only writers were the seed scripts — so an acquired
    // decision had no headnote at any layer.
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const headnote = 'Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder.';
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Bundesgerichtsurteil 9C_100/2025',
      body_text: 'Sachverhalt ...',
      metadata: { regeste: headnote },
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({ regeste: headnote }),
    );
  });

  it('reads the RIS headnote from extracted_metadata for a row published before the promotion', async () => {
    // A document already in canonical Delta carries `extracted_metadata.headnote`
    // (normalize/xml.py maps RIS `leitsatz`/`rechtssatz`/`strs` to it) but no promoted
    // `metadata.regeste`. Reading the fallback is what lets a reindex pick the headnote
    // up without reprocessing the corpus.
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const headnote = 'Die Asylgewährung an Wehrdienstverweigerer erfordert ...';
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'VwGH Ra 2024/19/0104',
      body_text: 'Begründung ...',
      metadata: { extracted_metadata: { headnote } },
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({ regeste: headnote }),
    );
  });

  it('leaves `regeste` unset when the source published no headnote', async () => {
    // The normal case: statutes and ordinances have none, and an empty string would
    // render as a blank headnote the reader takes as authoritative.
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Bundesverfassung',
      body_text: 'Art. 1 ...',
      metadata: { regeste: '   ' },
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    const projection = (repository.upsertProjection as ReturnType<typeof vi.fn>).mock
      .calls[0][0] as Record<string, unknown>;
    expect(projection.regeste).toBeUndefined();
  });

  it('indexes the document body as `content` so the highlighter can build a snippet', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const body =
      'Die Kündigungsfrist beträgt drei Monate. Ein Konkurrenzverbot ist nur verbindlich, ' +
      'wenn es schriftlich vereinbart wurde.';
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Obligationenrecht Auszug',
      body_text: body,
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({ content: body }),
    );
  });

  it('falls back to the concatenated section bodies when there is no body_text', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Zivilgesetzbuch Auszug',
      sections: [
        { section_id: 'sec_1', title: 'Art. 1', content: 'Erster Abschnitt zum Grundsatz.' },
        { section_id: 'sec_2', title: 'Art. 2', content: 'Zweiter Abschnitt zu Treu und Glauben.' },
      ],
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    const projection = (repository.upsertProjection as ReturnType<typeof vi.fn>).mock
      .calls[0][0] as { content?: string };
    expect(projection.content).toContain('Erster Abschnitt zum Grundsatz.');
    expect(projection.content).toContain('Zweiter Abschnitt zu Treu und Glauben.');
  });

  it('derives content_preview from the indexed body rather than replacing it', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const body = 'A'.repeat(900);
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Langes Dokument',
      body_text: body,
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    const projection = (repository.upsertProjection as ReturnType<typeof vi.fn>).mock
      .calls[0][0] as { content?: string; content_preview?: string };
    // The preview is truncated; the indexed body is not.
    expect(projection.content).toHaveLength(900);
    expect(projection.content_preview?.length).toBeLessThan(body.length);
  });

  // ── Citation graph: the NODE half (#582, ADR-0033) ──
  //
  // Before this, `extractCitationTargets` scanned only the NORMALIZED title and
  // `official_citation`. The Fedlex SPARQL provider sets no official_citation,
  // and normalization strips the "(SR 101)" suffix from the title — so a real
  // Fedlex law produced ZERO targets, `citation-targets` was never created, and
  // all 504 extracted citations stayed unresolved. These tests pin the fix.
  //
  // The lean document below mirrors the golden fixture
  // `document-intelligence/tests/golden/ch_fedlex_law_html/document.html`.

  it('indexes a Swiss law under its own SR number, taken from the raw title', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft (SR 101)',
      document_type: 'legislation',
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.bulkIndexCitationTargets).toHaveBeenCalledWith([
      expect.objectContaining({
        document_id: baseProcessedEvent.payload.document_id,
        identifier_type: 'sr',
        identifier_value: '101',
      }),
    ]);
  });

  it('indexes a Swiss law under the SR number in its masthead line', async () => {
    // Fedlex states the SR number in the opening line of the body, which is the
    // only deterministic source when the title carries no "(SR nnn)" suffix.
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Schweizerisches Zivilgesetzbuch',
      document_type: 'legislation',
      body_text:
        'Schweizerisches Zivilgesetzbuch vom 10. Dezember 1907 (Stand am 1. Januar 2024), SR 210.\n' +
        'Art. 1 Anwendung des Rechts ...',
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.bulkIndexCitationTargets).toHaveBeenCalledWith([
      expect.objectContaining({ identifier_type: 'sr', identifier_value: '210' }),
    ]);
  });

  // ── Short-title nodes (#594): what makes "Art. 36 BV" resolvable ──

  it('indexes a law under its short title and each of its articles', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft',
      document_type: 'legislation',
      // Fedlex nests the provider payload — `title_short` IS the abbreviation.
      body_text: JSON.stringify({
        inline_body: JSON.stringify({ provider: 'fedlex_sparql', title_short: 'BV' }),
      }),
      sections: [
        { section_id: 'sec_1', title: 'Art. 1 Schweizerische Eidgenossenschaft', anchor: 'art_1' },
        {
          section_id: 'sec_36',
          title: 'Art. 36 Einschränkungen von Grundrechten',
          anchor: 'art_36',
        },
        { section_id: 'sec_x', title: 'Titel 2: Grundrechte' },
      ],
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    const targets = (repository.bulkIndexCitationTargets as ReturnType<typeof vi.fn>).mock
      .calls[0][0];

    expect(targets).toContainEqual(
      expect.objectContaining({ identifier_type: 'abbrev', identifier_value: 'BV' }),
    );
    expect(targets).toContainEqual(
      expect.objectContaining({
        identifier_type: 'abbrev_art',
        identifier_value: 'BV/36',
        section_id: 'sec_36',
        section_anchor: 'art_36',
      }),
    );
    // A chapter heading is not an article and mints no provision node.
    expect(targets).not.toContainEqual(
      expect.objectContaining({ identifier_value: expect.stringContaining('Titel') }),
    );
  });

  it('mints no short-title node when the source publishes no short title', async () => {
    // No dictionary, no inference: if the corpus does not supply the
    // abbreviation, citations to it stay honestly unresolved.
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft (SR 101)',
      document_type: 'legislation',
      sections: [{ section_id: 'sec_36', title: 'Art. 36 Einschränkungen', anchor: 'art_36' }],
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    const targets = (repository.bulkIndexCitationTargets as ReturnType<typeof vi.fn>).mock
      .calls[0][0];
    expect(
      targets.every((t: { identifier_type: string }) => !t.identifier_type.startsWith('abbrev')),
    ).toBe(true);
  });

  it('does NOT let a decision become addressable AS the statute it discusses', async () => {
    // The mirror of the SR masthead hazard, for short titles.
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'BGer 1C_123/2022',
      document_type: 'decision',
      body_text: JSON.stringify({ title_short: 'BV' }),
      sections: [{ section_id: 'sec_1', title: 'Art. 36 BV wird ausgelegt' }],
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    const calls = (repository.bulkIndexCitationTargets as ReturnType<typeof vi.fn>).mock.calls;
    const targets = calls.length > 0 ? calls[0][0] : [];
    expect(
      targets.some((t: { identifier_type: string }) => t.identifier_type.startsWith('abbrev')),
    ).toBe(false);
  });

  it('does NOT let a document claim to BE a norm it merely cites', async () => {
    // The hazard the masthead window exists to prevent. A wrong edge is worse
    // than a missing one: if this decision registered itself as `sr:210`, every
    // citation of the civil code in the entire corpus would resolve to it.
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Urteil 5A_123/2024',
      document_type: 'decision',
      body_text:
        'Das Bundesgericht hat entschieden. '.repeat(30) +
        'Nach Art. 8 ZGB (SR 210) traegt die Beweislast ...',
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    // No targets at all — a decision declares no SR number of its own.
    expect(repository.bulkIndexCitationTargets).not.toHaveBeenCalled();
  });

  it('does not read an SR number from deep in a law body', async () => {
    // Same hazard, inside a law: an SR number past the masthead is a citation to
    // a DIFFERENT norm, not a self-declaration.
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Kantonales Hundegesetz',
      document_type: 'legislation',
      body_text: `${'Lorem ipsum dolor sit amet. '.repeat(40)}Es gilt das ZGB (SR 210).`,
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.bulkIndexCitationTargets).not.toHaveBeenCalled();
  });

  it('indexes Austrian BGBl citation targets from publication-organ sections', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: '"Produktdeklaration" - Erweiterung der Verwendung',
      sections: [
        {
          section_id: 'sec_pub_1',
          title: 'Kundmachungsorgan',
          content: 'BGBl. Nr. 43/1975 aufgehoben durch BGBl. Nr. 825/1994',
        },
      ],
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.bulkIndexCitationTargets).toHaveBeenCalledWith([
      expect.objectContaining({
        document_id: baseProcessedEvent.payload.document_id,
        identifier_type: 'at_bgbl',
        identifier_value: '43/1975',
      }),
    ]);
  });

  it('maps canonical published-document lean rows into projection metadata', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'BVGE 123/2024',
      document_type: 'decision',
      effective_date: '2024-06-01',
      jurisdiction_id: 'ch_zh',
      language: 'de',
      body_text: 'Kurzfassung des Urteils mit ausreichend Text für eine Vorschau.',
      metadata: {
        extracted_metadata: {
          structural_path: 'BGer › Zivilrecht',
        },
      },
      extensions: {
        citations: [{ id: 'c1' }],
      },
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'BVGE 123/2024',
        document_type: 'decision',
        effective_date: '2024-06-01',
        jurisdiction: 'CH',
        structural_path: 'BGer › Zivilrecht',
        citations_count: 1,
        content_preview: expect.stringContaining('Kurzfassung'),
      }),
    );
  });

  it('keeps Austrian corpus ids from being misclassified by substring matches', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: '"Produktdeklaration" - Erweiterung der Verwendung',
      jurisdiction_id: 'jur_at_federal',
      body_text: 'RIS Dokument mit Bundesrecht-Inhalt.',
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      payload: {
        ...baseProcessedEvent.payload,
        provenance: {
          ...baseProcessedEvent.payload.provenance,
          corpus_id: 'corpus_public_at_bundesrecht_small_batch',
        },
      },
    });

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        jurisdiction: 'AT',
      }),
    );
  });

  describe('language facet (#572)', () => {
    // The CH Fedlex constitution templates are per-language
    // (`fedlex_sparql_constitution_de`), but they all share the
    // language-free corpus id `corpus_public_ch_fedlex_constitution`.
    const constitutionEvent: DocumentProcessedEventDto = {
      ...baseProcessedEvent,
      payload: {
        ...baseProcessedEvent.payload,
        provenance: {
          ...baseProcessedEvent.payload.provenance,
          corpus_id: 'corpus_public_ch_fedlex_constitution',
        },
      },
    };

    it('indexes a German-template acquisition as language=de', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      // Lean document exactly as DI emits it for the German expression:
      // no top-level `language`, the acquired language lives in
      // `metadata.original_language`.
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
        title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
        jurisdiction_id: 'jur_ch_federal',
        body_text: 'Bundesverfassung der Schweizerischen Eidgenossenschaft / vom 18. April 1999',
        metadata: {
          original_language: 'de',
          translation_status: 'original',
        },
      });
      const service = new ProjectionsService(repository, diClient);

      await service.applyDocumentProcessed(constitutionEvent);

      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({
          jurisdiction: 'CH',
          language: 'de',
          original_language: 'de',
        }),
      );
    });

    it('never guesses a language from a corpus id without a language token', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
        title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft',
      });
      const service = new ProjectionsService(repository, diClient);

      await service.applyDocumentProcessed(constitutionEvent);

      // "constitution" contains the substring "it" — it must not be read
      // as Italian. Absent is correct here; wrong is not.
      const projection = (repository.upsertProjection as ReturnType<typeof vi.fn>).mock
        .calls[0][0] as { language?: string };
      expect(projection.language).toBeUndefined();
    });

    it('still honours an explicit language token in the corpus id', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
        title: 'Costituzione federale della Confederazione Svizzera',
      });
      const service = new ProjectionsService(repository, diClient);

      await service.applyDocumentProcessed({
        ...constitutionEvent,
        payload: {
          ...constitutionEvent.payload,
          provenance: {
            ...constitutionEvent.payload.provenance,
            corpus_id: 'corpus_public_ch_fedlex_constitution_it',
          },
        },
      });

      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({ language: 'it' }),
      );
    });
  });

  it('indexes citations stored on section metadata', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Austrian federal law',
      jurisdiction_id: 'at_federal',
      sections: [
        {
          section_id: 'sec_at_1',
          title: 'Produktdeklaration',
          ordinal: 0,
          depth: 0,
          content: 'Siehe BGBl. Nr. 43/1975.',
          metadata: {
            citations: [
              {
                text: 'BGBl. Nr. 43/1975',
                citation_type: 'at_bgbl',
                normalized_reference: 'at_bgbl:43/1975',
              },
            ],
          },
        },
      ],
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        citations_count: 1,
        sections_count: 1,
      }),
    );
    expect(repository.bulkIndexCitations).toHaveBeenCalledWith([
      expect.objectContaining({
        citation_text: 'BGBl. Nr. 43/1975',
        citation_type: 'at_bgbl',
        normalized_reference: 'at_bgbl:43/1975',
        source_section_id: 'sec_at_1',
      }),
    ]);
  });

  it('normalizes aliased document type hints from lean metadata before indexing', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      metadata: {
        source_defaults: {
          document_type_hint: 'statute',
        },
      },
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_5',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_4' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        document_type: 'law',
      }),
    );

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      metadata: {
        source_defaults: {
          document_type_hint: 'legislation',
        },
      },
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_5b',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_4b' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        document_type: 'law',
      }),
    );

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      metadata: {
        extracted_metadata: {
          document_type: 'urteil',
        },
      },
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_6',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_5' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        document_type: 'decision',
      }),
    );
  });

  it('falls back to LLM title when canonical title is a placeholder', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      metadata: {
        llm_extraction: {
          applied: true,
          title: 'Bundesgericht 2C_123/2024',
          structural_path: 'BGer › Öffentliches Recht',
        },
      },
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgericht 2C_123/2024',
      }),
    );
  });

  it('extracts embedded Fedlex titles from JSON-shaped lean bodies when the canonical title is a placeholder', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      body_text: JSON.stringify({
        title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
        body: 'Bundesverfassung ...',
      }),
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
      }),
    );
  });

  it('extracts embedded titles from array-shaped JSON lean bodies when the canonical title is a placeholder', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      body_text: JSON.stringify([
        {
          section: {
            title: 'Bundesgesetz über das Bundesgericht',
            body: 'BGG ...',
          },
        },
      ]),
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgesetz über das Bundesgericht',
      }),
    );
  });

  it('treats RIS placeholder titles as missing and falls back to embedded JSON titles', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'RIS Dokument',
      body_text: JSON.stringify({
        title: 'Bundesgesetz über das Bundesgericht',
        body: 'BGG ...',
      }),
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgesetz über das Bundesgericht',
      }),
    );
  });

  it('falls back to citation, substantive text, and structural-path tail for missing titles', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      metadata: {
        official_citation: 'BGE 150 II 10',
      },
      body_text: 'Kurz.\nDies ist eine ausreichend lange Titel-ähnliche Zeile.',
      structural_path: 'BGer › Zivilrecht',
    });
    await service.applyDocumentProcessed(baseProcessedEvent);
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: 'BGE 150 II 10' }),
    );

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      body_text: 'Kurz.\nDies ist eine ausreichend lange Titel-ähnliche Zeile.',
      structural_path: 'BGer › Zivilrecht',
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_3',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_2' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        title: 'Dies ist eine ausreichend lange Titel-ähnliche Zeile.',
      }),
    );

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      structural_path: 'BGer › Zivilrecht',
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_4',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_3' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: 'Zivilrecht' }),
    );
  });

  it('extracts structured Fedlex titles from JSON body payloads before using raw text fallback', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      body_text: JSON.stringify({
        final_url: 'https://fedlex.data.admin.ch/eli/cc/1999/404',
        inline_body: JSON.stringify({
          provider: 'fedlex_sparql',
          title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
          title_short: 'BV',
        }),
      }),
      metadata: {
        source_defaults: {
          authority_id: 'auth_fedlex',
          document_type_hint: 'legislation',
        },
      },
    });

    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_4b',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_fedlex' },
    });

    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
        document_type: 'law',
      }),
    );
  });

  it('applies projection with fallback fields when DI enrichment is unavailable', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue(null);
    const service = new ProjectionsService(repository, diClient);

    const result = await service.applyDocumentProcessed(baseProcessedEvent);

    expect(result.status).toBe('applied');
    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: `Document ${baseProcessedEvent.payload.document_id}`,
        authority_name: 'Fedlex',
        is_official: true,
        sections_count: 0,
        citations_count: 0,
        lifecycle_status: 'active',
      }),
    );
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });

  describe('record_kind discriminator (#425)', () => {
    it('tags primary-document projections with record_kind=legal_document', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
        title: 'Some Document',
        jurisdiction_id: 'ch_federal',
      });
      const service = new ProjectionsService(repository, diClient);

      await service.applyDocumentProcessed(baseProcessedEvent);

      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({
          record_kind: 'legal_document',
        }),
      );
    });

    it('derives jurisdiction_ids from canonical jurisdiction_id when array form is absent', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
        title: 'A',
        jurisdiction_id: 'jur_ch_federal',
      });
      const service = new ProjectionsService(repository, diClient);

      await service.applyDocumentProcessed(baseProcessedEvent);

      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({
          record_kind: 'legal_document',
          jurisdiction_ids: ['jur_ch_federal'],
        }),
      );
    });

    it('passes through canonical jurisdiction_ids + authority_ids arrays from the lean doc', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
        title: 'A',
        jurisdiction_ids: ['jur_ch_federal', 'jur_ch_zh', 'GARBAGE'],
        authority_ids: ['auth_fedlex'],
      });
      const service = new ProjectionsService(repository, diClient);

      await service.applyDocumentProcessed(baseProcessedEvent);

      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({
          jurisdiction_ids: ['jur_ch_federal', 'jur_ch_zh'],
          authority_ids: ['auth_fedlex'],
        }),
      );
    });
  });

  describe('commentary insight projection (#425)', () => {
    const validInsight = {
      insight_id: 'ins_01jq7c1ny0ffv8qdr1xwbejqb6',
      document_id: 'doc_01jq7bdptzqv3xs0c41xpw1ybg',
      document_revision: 3,
      processing_manifest_id: 'pm_01jq7bhgy7g0pkj4f1d03f8f8c',
      insight_type: 'referenced_provision',
      claim: 'References Art. 754 OR',
      display_text: 'Lehre als Haftungsnorm fuer Organe.',
      language: 'de',
      jurisdiction_id: 'jur_ch_federal',
      jurisdiction_ids: ['jur_ch_federal'],
      authority_ids: ['auth_fedlex'],
      source_document_ids: ['doc_01jq7bdptzqv3xs0c41xpw1ybg'],
      confidence: 0.78,
      review_state: 'machine_verified',
    };

    it('projects a commentary insight as record_kind=commentary_insight using insight_id as document_id', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      const service = new ProjectionsService(repository, diClient);

      await service.applyCommentaryInsight(validInsight);

      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({
          document_id: 'ins_01jq7c1ny0ffv8qdr1xwbejqb6',
          record_kind: 'commentary_insight',
          title: 'References Art. 754 OR',
          document_type: 'commentary',
          jurisdiction: 'CH',
          jurisdiction_ids: ['jur_ch_federal'],
          authority_ids: ['auth_fedlex'],
          source_document_ids: ['doc_01jq7bdptzqv3xs0c41xpw1ybg'],
          content_preview: 'Lehre als Haftungsnorm fuer Organe.',
          language: 'de',
        }),
      );
    });

    it('extracts commentary insights carried by the lean document during applyDocumentProcessed', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
        title: 'Primary doc',
        jurisdiction_id: 'jur_ch_federal',
        commentary_insights: [validInsight],
      });
      const service = new ProjectionsService(repository, diClient);

      await service.applyDocumentProcessed(baseProcessedEvent);

      // upsertProjection called twice: once for the primary document,
      // once for the commentary insight.
      expect(repository.upsertProjection).toHaveBeenCalledTimes(2);
      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({ record_kind: 'legal_document' }),
      );
      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({
          record_kind: 'commentary_insight',
          document_id: 'ins_01jq7c1ny0ffv8qdr1xwbejqb6',
        }),
      );
    });

    it('skips commentary insights missing required canonical id-list fields', async () => {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      const incomplete = { ...validInsight, source_document_ids: [] };
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
        title: 'Primary',
        jurisdiction_id: 'jur_ch_federal',
        commentary_insights: [incomplete],
      });
      const service = new ProjectionsService(repository, diClient);

      await service.applyDocumentProcessed(baseProcessedEvent);

      // Only the primary document is projected; the malformed
      // commentary insight is dropped.
      expect(repository.upsertProjection).toHaveBeenCalledTimes(1);
      expect(repository.upsertProjection).toHaveBeenCalledWith(
        expect.objectContaining({ record_kind: 'legal_document' }),
      );
    });
  });

  describe('norm hierarchy (#583, ADR-0033)', () => {
    /** Project a lean document and return the row that was written. */
    async function project(leanDocument: Record<string, unknown>) {
      const repository = createRepositoryMock();
      const diClient = createDocumentIntelligenceMock();
      (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue(leanDocument);
      const service = new ProjectionsService(repository, diClient);
      await service.applyDocumentProcessed(baseProcessedEvent);
      return (repository.upsertProjection as ReturnType<typeof vi.fn>).mock.calls[0][0];
    }

    it('gives a federal document the federal level', async () => {
      const row = await project({
        title: 'Tierschutzgesetz',
        jurisdiction_ids: ['jur_ch_federal'],
      });
      expect(row.level).toBe('federal');
    });

    it('gives a cantonal document the cantonal level and makes it subordinate to federal law', async () => {
      const row = await project({ title: 'Hundegesetz', jurisdiction_ids: ['jur_ch_zh'] });
      expect(row.level).toBe('cantonal');
      expect(row.subordinate_to).toContain('jur_ch_federal');
      expect(row.subordinate_to).not.toContain('jur_ch_zh');
    });

    it('gives a communal ordinance the municipal level, subordinate to its canton AND the federation', async () => {
      // The act being challenged in the dog question. Steps 2 and 3 of the walk
      // — is it authorised, is it preempted — are these two edges.
      const row = await project({
        title: 'Hundereglement',
        jurisdiction_ids: ['jur_ch_gemeinde_261'],
      });
      expect(row.level).toBe('municipal');
      expect(row.subordinate_to).toContain('jur_ch_zh');
      expect(row.subordinate_to).toContain('jur_ch_federal');
    });

    it('honours a declared `constitutional` level the jurisdiction cannot supply', async () => {
      const row = await project({
        title: 'Bundesverfassung',
        jurisdiction_ids: ['jur_ch_federal'],
        level: 'constitutional',
      });
      expect(row.level).toBe('constitutional');
    });

    it('leaves level unset for a jurisdiction the hierarchy does not know', async () => {
      const row = await project({ title: 'Unknown', jurisdiction_ids: ['jur_atlantis'] });
      expect(row.level).toBeUndefined();
      expect(row.subordinate_to).toBeUndefined();
    });

    it('falls back to effective_date for in_force_from so there is one field to range-query', async () => {
      const row = await project({
        title: 'Hundegesetz',
        jurisdiction_ids: ['jur_ch_zh'],
        effective_date: '2005-01-01',
      });
      expect(row.in_force_from).toBe('2005-01-01');
    });

    it('carries the repeal date so temporal validity is answerable', async () => {
      const row = await project({
        title: 'Altes Hundegesetz',
        jurisdiction_ids: ['jur_ch_zh'],
        effective_date: '2005-01-01',
        in_force_until: '2018-12-31',
      });
      expect(row.in_force_until).toBe('2018-12-31');
    });

    it('accepts `repealed_date` as an alias for the repeal date', async () => {
      const row = await project({
        title: 'Altes Hundegesetz',
        jurisdiction_ids: ['jur_ch_zh'],
        repealed_date: '2018-12-31',
      });
      expect(row.in_force_until).toBe('2018-12-31');
    });

    it('does not rank commentary in the hierarchy of norms', async () => {
      // Commentary is not a norm; it governs nothing.
      const repository = createRepositoryMock();
      const service = new ProjectionsService(repository, createDocumentIntelligenceMock());
      await service.applyCommentaryInsight({
        insight_id: 'doc_01jq7bhgy7g0pkj4f1d03f8f8d',
        document_id: 'doc_01jq7bhgy7g0pkj4f1d03f8f8c',
        document_revision: 1,
        processing_manifest_id: 'pm_01jq7bhgy7g0pkj4f1d03f8f8c',
        insight_type: 'summary',
        claim: 'A claim',
        display_text: 'Some text',
        jurisdiction_ids: ['jur_ch_zh'],
        authority_ids: ['auth_fedlex'],
        source_document_ids: ['doc_01jq7bhgy7g0pkj4f1d03f8f8c'],
        confidence: 0.9,
        review_state: 'approved',
      });
      const row = (repository.upsertProjection as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(row.level).toBeUndefined();
      expect(row.subordinate_to).toBeUndefined();
    });
  });
});

describe('ProjectionsService.resolveCitations (the write-path join)', () => {
  const bvArticle = {
    document_id: 'doc_bv',
    identifier_type: 'abbrev_art',
    identifier_value: 'BV/36',
    title: 'Bundesverfassung',
    document_type: 'law',
    section_id: 'sec_36',
    section_anchor: 'art_36',
  };

  function citation(overrides: Record<string, unknown> = {}) {
    return {
      citation_id: 'cit_1',
      source_document_id: 'doc_src',
      citation_text: 'Art. 36 BV',
      citation_type: 'article',
      normalized_reference: 'abbrev_art:BV/36',
      resolved: false,
      ...overrides,
    };
  }

  function serviceWith(candidates: Map<string, unknown[]> | Error) {
    const repository = createRepositoryMock();
    (repository.resolveCitationTargets as ReturnType<typeof vi.fn>).mockImplementation(() =>
      candidates instanceof Error ? Promise.reject(candidates) : Promise.resolve(candidates),
    );
    return new ProjectionsService(repository, createDocumentIntelligenceMock());
  }

  // POSITIVE. A wrong implementation that resolves nothing fails here.
  it('writes an edge when exactly one document answers the key', async () => {
    const service = serviceWith(new Map([['abbrev_art:BV/36', [bvArticle]]]));

    const [row] = await service.resolveCitations([citation()]);

    expect(row.target_document_id).toBe('doc_bv');
    expect(row.target_title).toBe('Bundesverfassung');
    expect(row.resolved).toBe(true);
    expect(row.resolution_status).toBe('resolved');
    expect(row.unresolved_reason).toBeUndefined();
  });

  // THE GUARD. Before this change the projection adapter built a
  // `Map<key, match>` and let the LAST search hit win, so this case was
  // persisted as `resolved: true` pointing at one arbitrary document.
  it('refuses to write an edge when several documents answer the key', async () => {
    const service = serviceWith(
      new Map([
        [
          'abbrev_art:EG/1',
          [
            { ...bvArticle, document_id: 'doc_zh', identifier_value: 'EG/1' },
            { ...bvArticle, document_id: 'doc_be', identifier_value: 'EG/1' },
          ],
        ],
      ]),
    );

    const [row] = await service.resolveCitations([
      citation({ normalized_reference: 'abbrev_art:EG/1' }),
    ]);

    expect(row.target_document_id).toBeUndefined();
    expect(row.resolved).toBe(false);
    expect(row.resolution_status).toBe('unresolved');
    expect(row.unresolved_reason).toBe('ambiguous');
  });

  // The three unresolved states must stay distinguishable on the persisted row.
  it('records a coverage gap as no_target_in_corpus', async () => {
    const service = serviceWith(new Map());

    const [row] = await service.resolveCitations([citation({ normalized_reference: 'sr:210' })]);

    expect(row.resolution_status).toBe('unresolved');
    expect(row.unresolved_reason).toBe('no_target_in_corpus');
  });

  it('records an extractor gap as not_normalizable', async () => {
    const service = serviceWith(new Map());

    const [row] = await service.resolveCitations([
      citation({ normalized_reference: undefined, citation_type: 'ch_paragraph' }),
    ]);

    expect(row.resolution_status).toBe('unresolved');
    expect(row.unresolved_reason).toBe('not_normalizable');
  });

  // UNKNOWN is not "no target". A failed lookup must leave the row without a
  // verdict rather than writing a coverage gap it did not observe (ADR-0052).
  it('writes no verdict at all when the targets lookup fails', async () => {
    const service = serviceWith(new Error('opensearch unavailable'));

    const [row] = await service.resolveCitations([citation()]);

    expect(row.resolution_status).toBeUndefined();
    expect(row.unresolved_reason).toBeUndefined();
    expect(row.resolved).toBe(false);
  });
});
