/**
 * Search integration tests — the real adapter against a REAL, seeded
 * OpenSearch (Testcontainers).
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * #672, #673 and #675 all shipped green. Each is a *convention mismatch*
 * between the query the API builds and the index it queries:
 *
 *   #672  case      — DTO lowercased `CH` -> `ch`; the index stores `CH` in a
 *                     case-sensitive `keyword`. The filter matched nothing, ever.
 *   #673  type      — `official_only=false` arrived as the STRING "false",
 *                     which is truthy, so the official-only filter was applied
 *                     while the UI read "Alle".
 *   #675  mapping   — aggregations targeted `.keyword` sub-fields the deployed
 *                     index does not have. OpenSearch returns empty buckets for
 *                     a non-existent field rather than erroring, so the facet
 *                     rail was permanently dead.
 *
 * None of the three is visible to a unit test, because every layer is
 * individually correct: the mapper maps, the DTO parses, the adapter builds a
 * well-formed query. They are only wrong *jointly*, against a real index. Every
 * e2e/VRT test in this repo uses `mockSearchApi`, so nothing in the suite had
 * ever met a real mapping or a real value convention.
 *
 * These tests therefore drive the FULL HTTP boundary — ValidationPipe, DTO,
 * controller, service, adapter — against a container with a seeded index, and
 * assert on observable search behaviour, never on the shape of the query body.
 * A test that asserts the query body is just the bug written twice.
 *
 * These tests run against the CANONICAL mapping only.
 *
 * An earlier revision of this file also ran every test against a `deployed`
 * shape — the canonical mapping with the `.keyword` sub-fields stripped, mirror-
 * ing the drifted live index. That was dropped deliberately. Asserting that
 * search must work against a drifted index makes the drift a supported
 * configuration, and the only way to satisfy both shapes is to weaken the
 * queries to the lowest common denominator — which is exactly the wrong fix
 * #675 first shipped (aggregating on bare field names, which then returns empty
 * buckets against any correctly-created index). The canonical mapping is the
 * contract; tests assert against the contract.
 *
 * The drifted shape is still covered — in `mapping-drift.integration.spec.ts`,
 * where its correct status is "this is drift, report it" rather than "this must
 * keep working". That file also asserts the real bootstrap path produces a
 * drift-free index, which is the guard that makes this file's premise true.
 */
import { type INestApplication, ValidationPipe } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { Test } from '@nestjs/testing';
import { Client } from '@opensearch-project/opensearch';
import request from 'supertest';
import { GenericContainer, type StartedTestContainer, Wait } from 'testcontainers';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { MetricsService } from '../../core/metrics/metrics.service';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import { documentsIndexDefinition } from '../../core/opensearch/documents-index.mapping';
import { SearchOpenSearchAdapter } from './opensearch.adapter';
import { SearchController } from './search.controller';
import { SEARCH_REPOSITORY } from './search.repository';
import { SearchService } from './search.service';

// Pinned to the image the local + self-hosted stacks run, so the test meets the
// same OpenSearch version production does.
const OPENSEARCH_IMAGE = 'opensearchproject/opensearch:2.17.1';
const INDEX = 'documents-integration';

/**
 * Corpus that mirrors the value conventions of the real index, because those
 * conventions ARE the thing under test:
 *   - `jurisdiction` uppercase ISO (`CH`) — the #672 trap
 *   - `language` lowercase (`de`)          — must keep working
 *   - a mix of `is_official` true/false    — the #673 trap
 *   - more than one `document_type`        — so facets have real buckets
 *
 * Every document matches the query "Recht" so a filter's effect is measurable
 * as a count difference rather than as a query-relevance artifact.
 */
const CORPUS = [
  {
    document_id: 'doc-ch-law-official-1',
    record_kind: 'legal_document',
    title: 'Bundesgesetz über das Recht der Hunde',
    content: 'Recht und Ordnung im Umgang mit Hunden.',
    jurisdiction: 'CH',
    jurisdiction_ids: ['jur_ch_federal'],
    authority_ids: ['auth_fedlex'],
    language: 'de',
    document_type: 'law',
    is_official: true,
  },
  {
    document_id: 'doc-ch-law-official-2',
    record_kind: 'legal_document',
    title: 'Verordnung zum Recht der Tierhaltung',
    content: 'Recht der Tierhaltung in der Gemeinde.',
    jurisdiction: 'CH',
    jurisdiction_ids: ['jur_ch_zh'],
    authority_ids: ['auth_fedlex'],
    language: 'de',
    document_type: 'law',
    is_official: true,
  },
  {
    document_id: 'doc-ch-decision-unofficial-1',
    record_kind: 'legal_document',
    title: 'Entscheid zum Recht auf Beschwerde',
    content: 'Recht auf Beschwerde gegen eine Verfügung.',
    jurisdiction: 'CH',
    jurisdiction_ids: ['jur_ch_federal'],
    authority_ids: ['auth_fedlex'],
    language: 'de',
    document_type: 'decision',
    is_official: false,
  },
  {
    document_id: 'doc-de-law-unofficial-1',
    record_kind: 'legal_document',
    title: 'Gesetz über das Recht der Halter',
    content: 'Recht der Halter von Tieren.',
    jurisdiction: 'DE',
    jurisdiction_ids: ['jur_de_federal'],
    authority_ids: ['auth_de_bgh'],
    language: 'de',
    document_type: 'law',
    is_official: false,
  },
] as const;

const CH_DOCS = CORPUS.filter((doc) => doc.jurisdiction === 'CH').length; // 3
const OFFICIAL_DOCS = CORPUS.filter((doc) => doc.is_official).length; // 2

let container: StartedTestContainer;
let client: Client;

beforeAll(async () => {
  container = await new GenericContainer(OPENSEARCH_IMAGE)
    .withExposedPorts(9200)
    .withEnvironment({
      'discovery.type': 'single-node',
      // Security plugin off: this container is throwaway and never leaves the
      // test network. Keeping it on would only add TLS/credential setup that
      // has nothing to do with what we are proving.
      DISABLE_SECURITY_PLUGIN: 'true',
      DISABLE_INSTALL_DEMO_CONFIG: 'true',
      OPENSEARCH_JAVA_OPTS: '-Xms512m -Xmx512m',
    })
    .withWaitStrategy(Wait.forHttp('/_cluster/health', 9200).forStatusCode(200))
    .withStartupTimeout(180_000)
    .start();

  client = new Client({
    node: `http://${container.getHost()}:${container.getMappedPort(9200)}`,
  });
}, 240_000);

afterAll(async () => {
  await client?.close();
  await container?.stop();
});

/** (Re)create the index from the canonical mapping and seed the corpus into it. */
async function seedIndex(): Promise<void> {
  const exists = await client.indices.exists({ index: INDEX });
  if (exists.body) {
    await client.indices.delete({ index: INDEX });
  }

  // Build from the canonical definition rather than a hand-copied mapping, so
  // this test tracks the source of truth instead of drifting from it.
  const definition = structuredClone(documentsIndexDefinition()) as {
    settings: Record<string, unknown>;
    mappings: { properties: Record<string, unknown> };
  };

  await client.indices.create({
    index: INDEX,
    // The client's generated body type is narrower than the mapping DSL the
    // canonical definition legitimately uses; the request itself is valid.
    body: definition as unknown as Parameters<typeof client.indices.create>[0]['body'],
  });

  await client.bulk({
    refresh: true,
    body: CORPUS.flatMap((doc) => [{ index: { _index: INDEX, _id: doc.document_id } }, doc]),
  });
}

/**
 * The real app wiring for the search surface: the same ValidationPipe options
 * as `main.ts` (transform on, implicit conversion off), the real controller,
 * service and OpenSearch adapter. Only the client is pointed at the container.
 * If the pipe config here drifts from `main.ts`, these tests stop proving
 * anything about production — keep them identical.
 */
async function createApp(): Promise<INestApplication> {
  const moduleRef = await Test.createTestingModule({
    imports: [
      ConfigModule.forRoot({
        load: [() => ({ opensearch: { documentsReadAlias: INDEX } })],
      }),
    ],
    controllers: [SearchController],
    providers: [
      SearchService,
      MetricsService,
      { provide: SEARCH_REPOSITORY, useClass: SearchOpenSearchAdapter },
      { provide: OPENSEARCH_CLIENT, useValue: client },
    ],
  }).compile();

  const app = moduleRef.createNestApplication();
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      transformOptions: { enableImplicitConversion: false },
    }),
  );
  await app.init();
  return app;
}

type SearchBody = {
  totalResults: number;
  results: { documentId?: string; document_id?: string }[];
  facets: { key: string; label: string; options: { value: string; count?: number }[] }[];
};

describe('search against a real seeded index (canonical mapping)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    await seedIndex();
    app = await createApp();
  }, 120_000);

  afterAll(async () => {
    await app?.close();
  });

  const search = async (query: string): Promise<SearchBody> => {
    const response = await request(app.getHttpServer()).get(`/v1/search?${query}`).expect(200);
    return response.body as SearchBody;
  };

  // ── #672: the jurisdiction filter must actually match ──

  it('matches documents when filtering by jurisdiction — the filter narrows, it does not annihilate', async () => {
    const unfiltered = await search('q=Recht');
    expect(unfiltered.totalResults).toBe(CORPUS.length);

    // Lowercase in the URL is the realistic case: the frontend workspace
    // sends `jurisdictions=ch` on boot. The API is responsible for
    // reconciling that with the index's uppercase convention (#672).
    const lower = await search('q=Recht&jurisdictions=ch');
    expect(lower.totalResults).toBe(CH_DOCS);

    // Uppercase must behave identically — the parameter is case-insensitive
    // to the caller even though the index is case-sensitive.
    const upper = await search('q=Recht&jurisdictions=CH');
    expect(upper.totalResults).toBe(CH_DOCS);

    // And it must genuinely discriminate, not just "return something".
    const other = await search('q=Recht&jurisdictions=de');
    expect(other.totalResults).toBe(CORPUS.length - CH_DOCS);
  });

  it('honours the singular `jurisdiction` parameter the same way', async () => {
    const result = await search('q=Recht&jurisdiction=ch');
    expect(result.totalResults).toBe(CH_DOCS);
  });

  it('matches on canonical jurisdiction and authority IDs', async () => {
    const byJurisdiction = await search('q=Recht&jurisdiction_ids=jur_ch_federal');
    expect(byJurisdiction.totalResults).toBe(2);

    const byAuthority = await search('q=Recht&authority_id=auth_de_bgh');
    expect(byAuthority.totalResults).toBe(1);
  });

  it('keeps the lowercase `languages` convention working', async () => {
    const result = await search('q=Recht&languages=de');
    expect(result.totalResults).toBe(CORPUS.length);
  });

  // ── #673: official_only=false must widen, not narrow ──

  it('treats official_only=false as a no-op and official_only=true as a filter', async () => {
    const omitted = await search('q=Recht');
    const explicitlyFalse = await search('q=Recht&official_only=false');
    const explicitlyTrue = await search('q=Recht&official_only=true');

    // The bug: `Boolean("false") === true`, so `false` filtered like `true`.
    expect(explicitlyFalse.totalResults).toBe(omitted.totalResults);
    expect(explicitlyTrue.totalResults).toBe(OFFICIAL_DOCS);

    // Guard against a corpus where the assertion above is vacuous: `true` and
    // `false` must be distinguishable at all for this test to mean anything.
    expect(explicitlyTrue.totalResults).toBeLessThan(explicitlyFalse.totalResults);
  });

  it('reproduces the boot request that returned zero results in production', async () => {
    // The exact query string the workspace fires on load. It returned 0 while
    // the corpus held matches — #672 and #673 compounding.
    const result = await search(
      'q=Recht&jurisdictions=ch&languages=de&official_only=false&page_size=25',
    );
    expect(result.totalResults).toBe(CH_DOCS);
    expect(result.results.length).toBe(CH_DOCS);
  });

  // ── #675: facets must come back non-empty ──

  it('returns non-empty facets with real buckets for every query', async () => {
    const result = await search('q=Recht');

    expect(result.facets.length).toBeGreaterThan(0);
    // Non-empty is not enough: a facet with zero options renders the same
    // dead rail. Every facet returned must carry buckets with counts.
    for (const facet of result.facets) {
      expect(facet.options.length).toBeGreaterThan(0);
      for (const option of facet.options) {
        expect(option.count).toBeGreaterThan(0);
      }
    }

    const keys = result.facets.map((facet) => facet.key);
    expect(keys).toEqual(expect.arrayContaining(['jurisdiction', 'document_type', 'language']));

    // The bucket values must be the real index values, not placeholders.
    const jurisdiction = result.facets.find((facet) => facet.key === 'jurisdiction');
    expect(jurisdiction?.options.map((option) => option.value).sort()).toEqual(['CH', 'DE']);

    const documentType = result.facets.find((facet) => facet.key === 'document_type');
    expect(documentType?.options.map((option) => option.value).sort()).toEqual(['decision', 'law']);
  });

  it('returns facets for a filtered result set too', async () => {
    const result = await search('q=Recht&jurisdictions=ch');
    expect(result.facets.length).toBeGreaterThan(0);
  });

  it('exposes non-empty aggregations on /v1/search/context', async () => {
    const response = await request(app.getHttpServer()).get('/v1/search/context').expect(200);
    const body = response.body as {
      jurisdictions: unknown[];
      languages: unknown[];
      sourceTypes: unknown[];
    };

    expect(body.jurisdictions.length).toBeGreaterThan(0);
    expect(body.languages.length).toBeGreaterThan(0);
    expect(body.sourceTypes.length).toBeGreaterThan(0);
  });
});
