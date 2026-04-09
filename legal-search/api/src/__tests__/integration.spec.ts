/**
 * API integration tests.
 *
 * These test the full HTTP pipeline: request → validation → service → mapper → response.
 * They validate that the BFF contract (ADR-0011) holds at the HTTP level:
 * - Array fields are always present (never undefined/null)
 * - Optional scalar fields are omitted when absent
 * - ViewModels have the expected composition (badges, actions, metadata)
 * - Unknown vocabulary values produce valid (generic) responses, not 500s
 * - Validation rejects malformed input
 */

import type { INestApplication } from '@nestjs/common';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import type { DocumentIntelligenceClient } from '../lib/document-intelligence/document-intelligence.client';
import type { DocumentsRepository } from '../modules/documents/documents.repository';
import type { ProjectionRepository } from '../modules/projections/projections.repository';
import type { SearchRepository } from '../modules/search/search.repository';
import { createTestApp, EMPTY_SEARCH } from './test-app';

// supertest CJS/ESM interop — vitest resolves default differently than tsc
// eslint-disable-next-line @typescript-eslint/no-var-requires
const supertest = require('supertest');

let app: INestApplication;
let searchRepo: SearchRepository;
let documentsRepo: DocumentsRepository;
let projectionsRepo: ProjectionRepository;

beforeAll(async () => {
  const testApp = await createTestApp({
    documentIntelligenceClient: {
      fetchLeanDocument: vi.fn().mockResolvedValue({ title: 'Lean projection title' }),
    },
  });
  app = testApp.app;
  searchRepo = testApp.searchRepo;
  documentsRepo = testApp.documentsRepo;
  projectionsRepo = testApp.projectionsRepo;
});

afterAll(async () => {
  await app?.close();
});

// ─── Search Response Contract ───

describe('search response contract (ADR-0011)', () => {
  it('results contain all required ViewModel fields', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search?q=test').expect(200);

    const result = res.body.results[0];

    // Required fields
    expect(result).toHaveProperty('id');
    expect(result).toHaveProperty('type');
    expect(result).toHaveProperty('title');
    expect(result).toHaveProperty('subtitle');
    expect(result).toHaveProperty('snippet');

    // Required arrays (never undefined, never null)
    expect(Array.isArray(result.badges)).toBe(true);
    expect(Array.isArray(result.metadataRows)).toBe(true);
    expect(Array.isArray(result.relatedCounts)).toBe(true);
    expect(Array.isArray(result.actions)).toBe(true);
  });

  it('law result has correct badge composition', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search?q=test').expect(200);

    const lawResult = res.body.results.find((r: { type: string }) => r.type === 'law');

    expect(lawResult.badges[0].label).toBe('Gesetz');
    expect(lawResult.badges[0].colorKey).toBe('blue');
    expect(lawResult.badges[0].iconKey).toBe('ch');
  });

  it('decision result has correct badge composition', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search?q=test').expect(200);

    const decisionResult = res.body.results.find((r: { type: string }) => r.type === 'decision');

    expect(decisionResult.badges[0].label).toBe('Gerichtsentscheid');
    expect(decisionResult.badges[0].colorKey).toBe('pink');
  });

  it('structuralContext is present when structural_path exists', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search?q=test').expect(200);

    const lawResult = res.body.results.find((r: { type: string }) => r.type === 'law');
    const decisionResult = res.body.results.find((r: { type: string }) => r.type === 'decision');

    // Law has structural_path → structuralContext present
    expect(lawResult.structuralContext).toBe('OR › Gesellschaftsrecht');

    // Decision has no structural_path → field omitted
    expect(decisionResult.structuralContext).toBeUndefined();
  });

  it('contentLanguage is present when language exists', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search?q=test').expect(200);

    const lawResult = res.body.results.find((r: { type: string }) => r.type === 'law');
    expect(lawResult.contentLanguage).toBeDefined();
    expect(lawResult.contentLanguage.display).toBe('de');
    expect(lawResult.contentLanguage.label).toBe('Originalsprache');
  });

  it('facets have proper structure', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search?q=test').expect(200);

    expect(res.body.facets.length).toBeGreaterThan(0);

    const facet = res.body.facets[0];
    expect(facet).toHaveProperty('key');
    expect(facet).toHaveProperty('label');
    expect(facet).toHaveProperty('type');
    expect(Array.isArray(facet.options)).toBe(true);

    const option = facet.options[0];
    expect(option).toHaveProperty('value');
    expect(option).toHaveProperty('label');
    expect(option).toHaveProperty('count');
  });

  it('empty search returns empty arrays, not null', async () => {
    (searchRepo.search as ReturnType<typeof vi.fn>).mockResolvedValueOnce(EMPTY_SEARCH);

    const res = await supertest(app.getHttpServer()).get('/v1/search?q=noresults').expect(200);

    expect(res.body.results).toEqual([]);
    expect(res.body.facets).toEqual([]);
    expect(res.body.totalResults).toBe(0);
  });
});

// ─── Search Context Contract ───

describe('search context contract', () => {
  it('jurisdictions have label, key, active, iconKey', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search/context').expect(200);

    const ch = res.body.jurisdictions[0];
    expect(ch.key).toBe('ch');
    expect(ch.label).toBe('Schweiz');
    expect(ch.active).toBe(true);
    expect(ch.iconKey).toBe('ch');
  });

  it('languages default DE to active', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search/context').expect(200);

    const de = res.body.languages.find((l: { key: string }) => l.key === 'de');
    const fr = res.body.languages.find((l: { key: string }) => l.key === 'fr');

    expect(de.active).toBe(true);
    expect(fr.active).toBe(false);
  });

  it('sourceTypes start with "Alle" as active', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search/context').expect(200);

    expect(res.body.sourceTypes[0]).toEqual({
      key: 'all',
      label: 'Alle',
      active: true,
    });
  });
});

// ─── Document Detail Contract ───

describe('document detail contract (ADR-0011)', () => {
  it('detail view has all required ViewModel fields', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/documents/doc_001').expect(200);

    expect(res.body.id).toBe('doc_001');
    expect(res.body.type).toBe('law');
    expect(res.body.title).toBe('Obligationenrecht');
    expect(typeof res.body.subtitle).toBe('string');

    // Required arrays
    expect(Array.isArray(res.body.metadata)).toBe(true);
    expect(Array.isArray(res.body.tabs)).toBe(true);
    expect(Array.isArray(res.body.relatedGroups)).toBe(true);
    expect(Array.isArray(res.body.references)).toBe(true);
    expect(Array.isArray(res.body.annotations)).toBe(true);
  });

  it('detail tabs include content and sections', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/documents/doc_001').expect(200);

    const tabKeys = res.body.tabs.map((t: { key: string }) => t.key);
    expect(tabKeys).toContain('content');
    expect(tabKeys).toContain('sections');
    expect(tabKeys).toContain('details');
  });

  it('detail references are grouped by citation type', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/documents/doc_001').expect(200);

    expect(res.body.references).toHaveLength(1);
    expect(res.body.references[0].label).toBe('statute_reference');
    expect(res.body.references[0].items[0].title).toBe('BGE 144 III 264');
  });

  it('breadcrumbs are split from structural_path', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/documents/doc_001').expect(200);

    expect(res.body.breadcrumbs).toEqual(['OR', 'Gesellschaftsrecht']);
  });

  it('returns 404 for missing document', async () => {
    (documentsRepo.getById as ReturnType<typeof vi.fn>).mockResolvedValueOnce(null);

    await supertest(app.getHttpServer()).get('/v1/documents/doc_nonexistent').expect(404);
  });
});

// ─── Document Service (mocked) ───

describe('document detail with Document Service client (ADR-0010)', () => {
  let diApp: INestApplication;

  beforeAll(async () => {
    const mockDi: DocumentIntelligenceClient = {
      fetchLeanDocument: vi.fn().mockResolvedValue({ schema_name: 'docling', lean: true }),
    };
    const testApp = await createTestApp({ documentIntelligenceClient: mockDi });
    diApp = testApp.app;
  });

  afterAll(async () => {
    await diApp?.close();
  });

  it('merges lean Docling into content when OpenSearch has no body fields', async () => {
    const res = await supertest(diApp.getHttpServer()).get('/v1/documents/doc_001').expect(200);

    expect(res.body.content).toEqual({ schema_name: 'docling', lean: true });
  });
});

// ─── Resilience: Unknown Vocabulary Values ───

describe('unknown vocabulary handling (ADR-0012)', () => {
  it('unknown document_type returns valid response, not 500', async () => {
    (searchRepo.search as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      total: 1,
      hits: [
        {
          document_id: 'doc_unknown',
          title: 'Regulation X',
          document_type: 'regulation', // not in vocabulary
          jurisdiction: 'XX', // not in vocabulary
        },
      ],
      aggregations: {},
    });

    const res = await supertest(app.getHttpServer()).get('/v1/search?q=regulation').expect(200);

    const result = res.body.results[0];
    // Falls back to generic — but still valid
    expect(result.badges[0].label).toBe('Dokument');
    expect(result.badges[0].colorKey).toBe('slate');
    expect(result.actions.length).toBeGreaterThan(0);
    // arrays are still arrays
    expect(Array.isArray(result.metadataRows)).toBe(true);
  });
});

// ─── Validation ───

describe('input validation', () => {
  it('rejects page_size above maximum', async () => {
    await supertest(app.getHttpServer()).get('/v1/search?q=test&page_size=200').expect(400);
  });

  it('rejects page below minimum', async () => {
    await supertest(app.getHttpServer()).get('/v1/search?q=test&page=0').expect(400);
  });
});

describe('projections event ingestion', () => {
  const processedEvent = {
    event_id: 'evt_01jq8bhgy7g0pkj4f1d03f8f8c',
    event_type: 'document.processed',
    event_version: 1,
    occurred_at: '2026-04-03T10:00:00Z',
    producer: 'document-intelligence',
    payload: {
      document_id: 'doc_01jq7bhgy7g0pkj4f1d03f8f8c',
      document_revision: 2,
      processing_manifest_id: 'pm_01jq7bhgy7g0pkj4f1d03f8f8c',
      processing_version: 'v1.0.0',
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

  const withdrawnEvent = {
    event_id: 'evt_01jq8chgy7g0pkj4f1d03f8f8c',
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
      reason_summary: 'manual withdraw',
      search_disposition: 'remove',
    },
  };

  it('accepts document.processed event and applies projection', async () => {
    const res = await supertest(app.getHttpServer())
      .post('/v1/projections/events/document-processed')
      .send(processedEvent)
      .expect(202);

    expect(res.body.status).toBe('applied');
  });

  it('returns ignored_duplicate for duplicate redelivery by event id', async () => {
    (projectionsRepo.hasHistoryEvent as ReturnType<typeof vi.fn>).mockResolvedValueOnce(true);

    const res = await supertest(app.getHttpServer())
      .post('/v1/projections/events/document-processed')
      .send(processedEvent)
      .expect(202);

    expect(res.body.status).toBe('ignored_duplicate');
  });

  it('accepts document.withdrawn event and de-indexes', async () => {
    const res = await supertest(app.getHttpServer())
      .post('/v1/projections/events/document-withdrawn')
      .send(withdrawnEvent)
      .expect(202);

    expect(res.body.status).toBe('applied');
  });
});
