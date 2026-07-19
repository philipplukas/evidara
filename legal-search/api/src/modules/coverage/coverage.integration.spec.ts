/**
 * Coverage integration tests — the real adapter against a REAL, seeded
 * OpenSearch (Testcontainers).
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * A coverage endpoint has a uniquely bad failure mode: when it is broken it
 * says "we hold nothing", which is indistinguishable from the correct answer
 * when we genuinely hold nothing. #675 is the precedent — an aggregation on a
 * field with no `.keyword` sub-field returns EMPTY BUCKETS rather than an
 * error, and the facet rail was dead for months without a single red test.
 *
 * Applied to `/v1/coverage`, that same mistake produces a **false refusal**: an
 * agent told the corpus holds no federal law would correctly decline to answer,
 * and nobody would ever learn the corpus was full. The unit specs pin the query
 * shape, but as `search.integration.spec.ts` puts it, a test that asserts the
 * query body is just the bug written twice. Only a real index proves buckets
 * actually come back.
 *
 * So these tests assert observable coverage behaviour over a seeded corpus with
 * known contents, against the CANONICAL mapping.
 */
import { type INestApplication, ValidationPipe } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { Test } from '@nestjs/testing';
import { Client } from '@opensearch-project/opensearch';
import request from 'supertest';
import { GenericContainer, type StartedTestContainer, Wait } from 'testcontainers';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import { documentsIndexDefinition } from '../../core/opensearch/documents-index.mapping';
import { CoverageController } from './coverage.controller';
import { COVERAGE_REPOSITORY } from './coverage.repository';
import { CoverageService } from './coverage.service';
import type { CorpusCoverageView } from './entities/coverage.entities';
import { CoverageOpenSearchAdapter } from './opensearch.adapter';

const OPENSEARCH_IMAGE = 'opensearchproject/opensearch:2.17.1';
const INDEX = 'coverage-integration';

/**
 * A corpus with known, deliberately uneven contents:
 *   - CH federal: 3 norms, one of them repealed, one carrying no authority
 *   - CH ZH cantonal: 0 norms  — the refusal case, and the #709 scenario
 *   - one commentary row       — must not count as coverage
 * Two source versions, so provenance has something to report.
 */
const CORPUS = [
  {
    document_id: 'doc-bv',
    record_kind: 'legal_document',
    title: 'Bundesverfassung',
    content: 'Tierschutz und Grundrechte.',
    jurisdiction: 'CH',
    jurisdiction_ids: ['jur_ch_federal'],
    authority_ids: ['auth_fedlex'],
    level: 'constitutional',
    document_type: 'constitution',
    language: 'de',
    is_official: true,
    source_version_id: 'sv_fedlex_1',
    processed_at: '2026-07-10T00:00:00.000Z',
    in_force_from: '2000-01-01',
  },
  {
    document_id: 'doc-tschg',
    record_kind: 'legal_document',
    title: 'Tierschutzgesetz',
    content: 'Schutz der Tiere.',
    jurisdiction: 'CH',
    jurisdiction_ids: ['jur_ch_federal'],
    authority_ids: ['auth_fedlex'],
    level: 'federal',
    document_type: 'law',
    language: 'de',
    is_official: true,
    source_version_id: 'sv_fedlex_2',
    // The newest ingest in the federal group — `last_processed_at` must be this.
    processed_at: '2026-07-18T09:12:00.000Z',
    in_force_from: '2008-09-01',
  },
  {
    document_id: 'doc-repealed',
    record_kind: 'legal_document',
    title: 'Aufgehobenes Bundesgesetz',
    content: 'Nicht mehr in Kraft.',
    jurisdiction: 'CH',
    jurisdiction_ids: ['jur_ch_federal'],
    // No `authority_ids` at all — the sparse-authority case that
    // `documents_without_group_key` exists to surface.
    level: 'federal',
    document_type: 'law',
    language: 'de',
    is_official: true,
    source_version_id: 'sv_fedlex_1',
    processed_at: '2026-07-01T00:00:00.000Z',
    in_force_from: '1990-01-01',
    in_force_until: '2005-12-31',
  },
  {
    document_id: 'ins-commentary',
    record_kind: 'commentary_insight',
    title: 'Kommentar zum Tierschutzgesetz',
    content: 'Kommentar.',
    jurisdiction: 'CH',
    jurisdiction_ids: ['jur_ch_federal'],
    authority_ids: ['auth_commentary'],
    level: 'federal',
    document_type: 'commentary',
    language: 'de',
    is_official: false,
    source_version_id: 'sv_commentary_1',
    processed_at: '2026-07-19T00:00:00.000Z',
  },
];

let container: StartedTestContainer;
let client: Client;

beforeAll(async () => {
  container = await new GenericContainer(OPENSEARCH_IMAGE)
    .withExposedPorts(9200)
    .withEnvironment({
      'discovery.type': 'single-node',
      DISABLE_SECURITY_PLUGIN: 'true',
      DISABLE_INSTALL_DEMO_CONFIG: 'true',
      OPENSEARCH_JAVA_OPTS: '-Xms512m -Xmx512m',
    })
    .withWaitStrategy(Wait.forHttp('/_cluster/health', 9200).forStatusCodeMatching((c) => c < 500))
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

async function seedIndex(): Promise<void> {
  const exists = await client.indices.exists({ index: INDEX });
  if (exists.body) await client.indices.delete({ index: INDEX });

  // Built from the canonical definition, so this test tracks the source of
  // truth rather than drifting from it.
  const definition = structuredClone(documentsIndexDefinition());
  await client.indices.create({
    index: INDEX,
    body: definition as unknown as Parameters<typeof client.indices.create>[0]['body'],
  });

  await client.bulk({
    refresh: true,
    body: CORPUS.flatMap((doc) => [{ index: { _index: INDEX, _id: doc.document_id } }, doc]),
  });
}

async function createApp(): Promise<INestApplication> {
  const moduleRef = await Test.createTestingModule({
    imports: [
      ConfigModule.forRoot({ load: [() => ({ opensearch: { documentsReadAlias: INDEX } })] }),
    ],
    controllers: [CoverageController],
    providers: [
      CoverageService,
      { provide: COVERAGE_REPOSITORY, useClass: CoverageOpenSearchAdapter },
      { provide: OPENSEARCH_CLIENT, useValue: client },
    ],
  }).compile();

  const app = moduleRef.createNestApplication();
  // Identical to `main.ts`. If this drifts, the test stops proving anything
  // about production.
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

describe('coverage against a real seeded index (canonical mapping)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    await seedIndex();
    app = await createApp();
  }, 120_000);

  afterAll(async () => {
    await app?.close();
  });

  const coverage = async (query = ''): Promise<CorpusCoverageView> => {
    const response = await request(app.getHttpServer())
      .get(`/v1/coverage${query ? `?${query}` : ''}`)
      .expect(200);
    return response.body as CorpusCoverageView;
  };

  it('returns non-empty buckets — the aggregation fields resolve against the real mapping', async () => {
    // The #675 guard. A missing field yields empty buckets and no error, which
    // would present as "the corpus holds nothing" — a false refusal.
    const view = await coverage();

    expect(view.groups.length).toBeGreaterThan(0);
    const federal = view.groups.find((g) => g.key === 'jur_ch_federal');
    expect(federal?.holding).toBe('held');
    expect(federal?.documents).toBe(3);
  });

  it('aggregates on every dimension without returning an empty result', async () => {
    for (const dimension of ['jurisdiction', 'authority', 'document_type', 'level']) {
      const view = await coverage(`group_by=${dimension}`);
      expect(view.groups.length, `dimension ${dimension} produced no buckets`).toBeGreaterThan(0);
    }
  });

  it('reports a named jurisdiction we hold nothing for as not_held — the #709 refusal', async () => {
    // This is the whole point. `jur_ch_zh` is a real jurisdiction with nothing
    // indexed; the caller is told so positively rather than handed an empty list.
    const view = await coverage('jurisdiction_id=jur_ch_zh');

    expect(view.groups).toHaveLength(1);
    expect(view.groups[0]).toMatchObject({ key: 'jur_ch_zh', documents: 0, holding: 'not_held' });
    expect(view.groups[0].last_processed_at).toBeUndefined();
  });

  it('excludes commentary from coverage — it is not a norm', async () => {
    const view = await coverage();

    // 3 legal documents, not 4. Counting the commentary row would report the
    // corpus as holding law it does not hold.
    expect(view.total_documents).toBe(3);
    expect(view.groups.find((g) => g.key === 'jur_ch_federal')?.documents).toBe(3);
  });

  it('reports freshness as the newest ingest in the group', async () => {
    const view = await coverage('jurisdiction_id=jur_ch_federal');

    expect(view.groups[0].last_processed_at).toBe('2026-07-18T09:12:00.000Z');
  });

  it('reports the source versions behind the group', async () => {
    const view = await coverage('jurisdiction_id=jur_ch_federal');

    expect(view.groups[0].source_version_ids?.sort()).toEqual(['sv_fedlex_1', 'sv_fedlex_2']);
    expect(view.groups[0].source_version_count).toBe(2);
  });

  it('counts documents that carry no value for the grouping field', async () => {
    // `doc-repealed` has no `authority_ids`, so grouping by authority omits it.
    // Reported rather than silently dropped.
    const view = await coverage('group_by=authority');

    expect(view.documents_without_group_key).toBe(1);
    expect(view.total_documents).toBe(3);
  });

  it('keeps unknown-dated norms under in_force_at and says how many are assumed', async () => {
    // `doc-repealed` ended 2005 and must drop out; the other two survive. Their
    // in-force standing rests on a missing `in_force_until`, and the response
    // says so rather than presenting it as known.
    const view = await coverage('jurisdiction_id=jur_ch_federal&in_force_at=2019-06-01');

    expect(view.groups[0].documents).toBe(2);
    expect(view.groups[0].documents_without_repeal_date).toBe(2);
  });

  it('separates an unrecognized jurisdiction id from one we simply hold nothing for', async () => {
    const view = await coverage('jurisdiction_id=jur_ch_zurich');

    // A typo must not come back as a coverage fact.
    expect(view.unrecognized_jurisdiction_ids).toEqual(['jur_ch_zurich']);
    expect(view.groups).toHaveLength(0);
  });

  it('rejects an unknown group_by and an unknown level rather than widening the scope', async () => {
    await request(app.getHttpServer()).get('/v1/coverage?group_by=topic').expect(400);
    await request(app.getHttpServer()).get('/v1/coverage?level=galactic').expect(400);
  });

  it('declares its basis as the index on every response', async () => {
    const view = await coverage();

    expect(view.basis).toBe('index');
    expect(view.as_of).toBeTruthy();
  });
});
