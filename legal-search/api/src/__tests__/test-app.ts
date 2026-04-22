/**
 * Shared test setup for API integration tests.
 *
 * Creates a real NestJS application with mock repositories injected.
 * The app has the same global pipes and config as production (main.ts),
 * but with no OpenSearch dependency.
 *
 * Note: We build the module from individual pieces instead of importing
 * AppModule because vitest's transform (oxc/esbuild) does not emit
 * decorator metadata. By registering providers explicitly we avoid the
 * NestJS DI resolution issue with emitDecoratorMetadata.
 */
import 'reflect-metadata';
import { type INestApplication, ValidationPipe } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { Test } from '@nestjs/testing';
import { vi } from 'vitest';
import documentIntelligenceConfig from '../core/config/document-intelligence.config';
import opensearchConfig from '../core/config/opensearch.config';
import { OPENSEARCH_CLIENT } from '../core/opensearch/client';
import {
  DOCUMENT_INTELLIGENCE_CLIENT,
  type DocumentIntelligenceClient,
  NoopDocumentIntelligenceClient,
} from '../lib/document-intelligence/document-intelligence.client';
import { DocumentsController } from '../modules/documents/documents.controller';
import type { DocumentsRepository } from '../modules/documents/documents.repository';
import { DOCUMENTS_REPOSITORY } from '../modules/documents/documents.repository';
import { DocumentsService } from '../modules/documents/documents.service';
import { HealthController } from '../modules/health/health.controller';
import { ProjectionsController } from '../modules/projections/projections.controller';
import {
  PROJECTION_REPOSITORY,
  type ProjectionRepository,
} from '../modules/projections/projections.repository';
import { ProjectionsService } from '../modules/projections/projections.service';
import type {
  ContextAggregations,
  SearchResultEntity,
} from '../modules/search/entities/search.entities';
import { SearchController } from '../modules/search/search.controller';
import type { SearchRepository } from '../modules/search/search.repository';
import { SEARCH_REPOSITORY } from '../modules/search/search.repository';
import { SearchService } from '../modules/search/search.service';

// ─── Default Mock Data ───

const EMPTY_SEARCH: SearchResultEntity = {
  total: 0,
  hits: [],
  aggregations: {},
};

const SEARCH_WITH_RESULTS: SearchResultEntity = {
  total: 2,
  hits: [
    {
      document_id: 'doc_001',
      title: 'Obligationenrecht',
      snippet: 'Art. 1 OR',
      jurisdiction: 'CH',
      document_type: 'law',
      effective_date: '2024-01-01',
      structural_path: 'OR › Gesellschaftsrecht',
      language: 'de',
      sections_count: 42,
      citations_count: 15,
      related_commentary_count: 8,
      related_decisions_count: 23,
    },
    {
      document_id: 'doc_002',
      title: 'BGE 144 III 264',
      snippet: 'Verantwortlichkeit',
      jurisdiction: 'CH',
      document_type: 'decision',
      effective_date: '2018-06-15',
    },
  ],
  aggregations: {
    jurisdiction: [{ key: 'CH', doc_count: 2 }],
    document_type: [
      { key: 'law', doc_count: 1 },
      { key: 'decision', doc_count: 1 },
    ],
  },
};

const CONTEXT_AGGS: ContextAggregations = {
  jurisdictions: [{ key: 'CH', doc_count: 500 }],
  languages: [
    { key: 'de', doc_count: 400 },
    { key: 'fr', doc_count: 100 },
  ],
  source_types: [
    { key: 'law', doc_count: 300 },
    { key: 'decision', doc_count: 200 },
  ],
};

// ─── Test App Factory ───

export interface TestApp {
  app: INestApplication;
  searchRepo: SearchRepository;
  documentsRepo: DocumentsRepository;
  projectionsRepo: ProjectionRepository;
}

export async function createTestApp(overrides?: {
  searchRepo?: Partial<SearchRepository>;
  documentsRepo?: Partial<DocumentsRepository>;
  projectionsRepo?: Partial<ProjectionRepository>;
  documentIntelligenceClient?: DocumentIntelligenceClient;
}): Promise<TestApp> {
  const searchRepo: SearchRepository = {
    search: vi.fn().mockResolvedValue(SEARCH_WITH_RESULTS),
    getContextAggregations: vi.fn().mockResolvedValue(CONTEXT_AGGS),
    ...overrides?.searchRepo,
  };

  const documentsRepo: DocumentsRepository = {
    getById: vi.fn().mockResolvedValue({
      document_id: 'doc_001',
      title: 'Obligationenrecht',
      document_type: 'law',
      jurisdiction: 'CH',
      effective_date: '2024-01-01',
      language: 'de',
      structural_path: 'OR › Gesellschaftsrecht',
      sections_count: 2,
      citations_count: 1,
    }),
    getSections: vi.fn().mockResolvedValue([
      {
        section_id: 'sec_001',
        document_id: 'doc_001',
        title: 'Allgemeine Bestimmungen',
        ordinal: 0,
        depth: 0,
      },
    ]),
    getCitations: vi.fn().mockResolvedValue([
      {
        citation_id: 'cit_001',
        source_document_id: 'doc_001',
        target_document_id: 'doc_010',
        target_title: 'BGE 144 III 264',
        citation_text: 'Art. 716a OR',
        citation_type: 'statute_reference',
        resolved: true,
      },
    ]),
    getCitedBy: vi.fn().mockResolvedValue([]),
    ...overrides?.documentsRepo,
  };
  const projectionsRepo: ProjectionRepository = {
    hasHistoryEvent: vi.fn().mockResolvedValue(false),
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
    getHistoryStats: vi
      .fn()
      .mockResolvedValue({
        totalEvents: 0,
        applied: 0,
        stale: 0,
        ignoredDuplicate: 0,
        uniqueDocuments: 0,
      }),
    ...overrides?.projectionsRepo,
  };

  // Build the module explicitly — avoids decorator metadata issues
  // with vitest's oxc/esbuild transform which doesn't emit metadata.
  const diClient =
    overrides?.documentIntelligenceClient ?? new NoopDocumentIntelligenceClient();

  const moduleRef = await Test.createTestingModule({
    imports: [
      ConfigModule.forRoot({ isGlobal: true, load: [opensearchConfig, documentIntelligenceConfig] }),
    ],
    controllers: [HealthController, SearchController, DocumentsController, ProjectionsController],
    providers: [
      SearchService,
      DocumentsService,
      ProjectionsService,
      { provide: SEARCH_REPOSITORY, useValue: searchRepo },
      { provide: DOCUMENTS_REPOSITORY, useValue: documentsRepo },
      { provide: PROJECTION_REPOSITORY, useValue: projectionsRepo },
      { provide: DOCUMENT_INTELLIGENCE_CLIENT, useValue: diClient },
      {
        provide: OPENSEARCH_CLIENT,
        useValue: { ping: vi.fn().mockResolvedValue({}) },
      },
    ],
  }).compile();

  const app = moduleRef.createNestApplication();

  // Apply the same global config as main.ts
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      transformOptions: { enableImplicitConversion: false },
    }),
  );

  await app.init();

  return { app, searchRepo, documentsRepo, projectionsRepo };
}

export { CONTEXT_AGGS, EMPTY_SEARCH, SEARCH_WITH_RESULTS };
