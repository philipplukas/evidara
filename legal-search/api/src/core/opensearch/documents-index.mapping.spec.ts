import { describe, expect, it, vi } from 'vitest';
import type { DocumentIntelligenceClient } from '../../lib/document-intelligence/document-intelligence.client';
import type { DocumentProcessedEventDto } from '../../modules/projections/dto/projection-events.dto';
import type {
  CommentaryInsightInput,
  ProjectionRepository,
  SearchProjectionDocument,
} from '../../modules/projections/projections.repository';
import { ProjectionsService } from '../../modules/projections/projections.service';
import { buildAliasActions, deriveDocumentsPhysicalIndex } from './documents-bootstrap';
import { DOCUMENTS_INDEX_PROPERTIES, documentsIndexFields } from './documents-index.mapping';

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

/** Rich lean document that drives every optional projection field. */
const RICH_LEAN_DOCUMENT = {
  title: 'Urteil des Obergerichts',
  language: 'de',
  document_type: 'decision',
  effective_date: '2020-01-01',
  structural_path: 'Kanton ZH › Obergericht › Zivilrecht',
  jurisdiction_id: 'jur_ch_zh',
  jurisdiction_ids: ['jur_ch_zh'],
  authority_ids: ['auth_fedlex'],
  metadata: {
    official_citation: 'BGE 144 III 264',
    original_language: 'de',
    translation_status: 'original',
  },
  sections: [{ section_id: 'sec_1', title: 'Sachverhalt', ordinal: 0, depth: 0, content: 'text' }],
  citations: [{ citation_id: 'cit_1', text: 'Art. 41 OR' }],
};

const PROCESSED_EVENT: DocumentProcessedEventDto = {
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

const COMMENTARY_INSIGHT: CommentaryInsightInput = {
  insight_id: 'ins_01jq7bhgy7g0pkj4f1d03f8f8c',
  document_id: 'doc_01jq7bhgy7g0pkj4f1d03f8f8c',
  document_revision: 1,
  processing_manifest_id: 'pm_01jq7bhgy7g0pkj4f1d03f8f8c',
  insight_type: 'principle',
  claim: 'Treu und Glauben gilt auch im Prozessrecht.',
  display_text: 'Der Grundsatz von Treu und Glauben …',
  language: 'de',
  jurisdiction_id: 'jur_ch_federal',
  jurisdiction_ids: ['jur_ch_federal'],
  authority_ids: ['auth_fedlex'],
  source_document_ids: ['doc_01jq7bhgy7g0pkj4f1d03f8f8c'],
  confidence: 0.9,
  review_state: 'approved',
  occurred_at: '2026-04-03T10:00:00Z',
};

async function captureProjection(
  drive: (service: ProjectionsService) => Promise<unknown>,
  leanDocument: unknown,
): Promise<SearchProjectionDocument> {
  const repository = createRepositoryMock();
  const diClient: DocumentIntelligenceClient = {
    fetchLeanDocument: vi.fn().mockResolvedValue(leanDocument),
  };
  const service = new ProjectionsService(repository, diClient);
  await drive(service);
  const upsert = repository.upsertProjection as ReturnType<typeof vi.fn>;
  expect(upsert).toHaveBeenCalled();
  return upsert.mock.calls[0][0] as SearchProjectionDocument;
}

describe('canonical documents mapping', () => {
  it('covers every field ProjectionsService.buildProjection writes', async () => {
    const projection = await captureProjection(
      (service) => service.applyDocumentProcessed(PROCESSED_EVENT),
      RICH_LEAN_DOCUMENT,
    );

    const fields = new Set(documentsIndexFields());
    const missing = Object.keys(projection).filter((key) => !fields.has(key));
    expect(missing).toEqual([]);

    // Guard: the rich fixture must actually exercise the optional fields,
    // otherwise the assertion above passes vacuously.
    for (const key of ['document_type', 'effective_date', 'structural_path', 'authority_ids']) {
      expect(projection).toHaveProperty(key);
    }
  });

  it('covers every field buildCommentaryProjection writes (record_kind, id-lists)', async () => {
    const projection = await captureProjection(
      (service) => service.applyCommentaryInsight(COMMENTARY_INSIGHT),
      {},
    );

    const fields = new Set(documentsIndexFields());
    const missing = Object.keys(projection).filter((key) => !fields.has(key));
    expect(missing).toEqual([]);

    expect(projection.record_kind).toBe('commentary_insight');
    for (const key of ['source_document_ids', 'jurisdiction_ids', 'authority_ids']) {
      expect(projection).toHaveProperty(key);
    }
  });

  it('covers the richer OpenCaseLaw seed-only fields', () => {
    const fields = new Set(documentsIndexFields());
    for (const key of [
      'court',
      'docket_number',
      'regeste',
      'content',
      'related_decisions_count',
      'related_commentary_count',
    ]) {
      expect(fields.has(key)).toBe(true);
    }
  });

  it('declares a `.keyword` sub-field on every faceted/filtered field', () => {
    // The search adapter aggregates on `<field>.keyword` and filters on
    // the bare field or `<field>.keyword`.
    for (const field of [
      'jurisdiction',
      'document_type',
      'language',
      'jurisdiction_ids',
      'authority_ids',
    ]) {
      const definition = DOCUMENTS_INDEX_PROPERTIES[
        field as keyof typeof DOCUMENTS_INDEX_PROPERTIES
      ] as { type: string; fields?: { keyword?: { type: string } } };
      expect(definition.type).toBe('keyword');
      expect(definition.fields?.keyword?.type).toBe('keyword');
    }
  });

  it('keeps the German legal_text analyzer on the primary text fields', () => {
    for (const field of ['title', 'content', 'regeste']) {
      const definition = DOCUMENTS_INDEX_PROPERTIES[
        field as keyof typeof DOCUMENTS_INDEX_PROPERTIES
      ] as { type: string; analyzer?: string };
      expect(definition.type).toBe('text');
      expect(definition.analyzer).toBe('legal_text');
    }
  });
});

describe('documents alias bootstrap', () => {
  it('derives a physical index distinct from both aliases', () => {
    expect(deriveDocumentsPhysicalIndex('documents-read')).toBe('documents-000001');
    expect(deriveDocumentsPhysicalIndex('evidara-docs')).toBe('evidara-docs-000001');
  });

  it('points the read and write aliases at the SAME physical index', () => {
    const actions = buildAliasActions('documents-000001', 'documents-read', 'documents-write');
    const adds = actions
      .filter((a) => 'add' in a)
      .map((a) => (a as { add: { index: string; alias: string } }).add);

    const readAdd = adds.find((a) => a.alias === 'documents-read');
    const writeAdd = adds.find((a) => a.alias === 'documents-write');
    expect(readAdd?.index).toBe('documents-000001');
    expect(writeAdd?.index).toBe('documents-000001');
    expect(readAdd?.index).toBe(writeAdd?.index);
  });

  it('removes stale write-alias targets before re-pointing', () => {
    const actions = buildAliasActions(
      'documents-000002',
      'documents-read',
      'documents-write',
      [],
      ['documents-000001'],
    );
    expect(actions).toContainEqual({
      remove: { index: 'documents-000001', alias: 'documents-write' },
    });
  });
});
