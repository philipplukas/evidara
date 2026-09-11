/**
 * Smoke tests.
 *
 * "Does it start? Does it respond? Are the basic shapes correct?"
 *
 * These run against a real NestJS app with mock repositories.
 * If these fail, something fundamental is broken.
 */

import type { INestApplication } from '@nestjs/common';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createTestApp } from './test-app';

// supertest CJS/ESM interop — vitest resolves default differently than tsc
// eslint-disable-next-line @typescript-eslint/no-var-requires
const supertest = require('supertest');

let app: INestApplication;

beforeAll(async () => {
  const testApp = await createTestApp();
  app = testApp.app;
});

afterAll(async () => {
  await app?.close();
});

// ─── Health ───

describe('GET /health', () => {
  it('returns 200 with status ok', async () => {
    const res = await supertest(app.getHttpServer()).get('/health').expect(200);

    expect(res.body.status).toBe('ok');
    expect(res.body.timestamp).toBeDefined();
  });
});

// ─── Search ───

describe('GET /v1/search', () => {
  it('returns 200 with results array', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search?q=test').expect(200);

    expect(res.body).toHaveProperty('results');
    expect(res.body).toHaveProperty('facets');
    expect(res.body).toHaveProperty('totalResults');
    expect(Array.isArray(res.body.results)).toBe(true);
    expect(Array.isArray(res.body.facets)).toBe(true);
    expect(typeof res.body.totalResults).toBe('number');
  });

  it('returns 400 when q is missing', async () => {
    await supertest(app.getHttpServer()).get('/v1/search').expect(400);
  });

  // #986 / #984: the refusal has to survive serialization, not just exist in
  // the service. The test-app's corpus holds `jur_ch_zh` and `jur_ch_federal`.
  it('carries a refusal to the wire when the query names a canton the corpus lacks', async () => {
    const res = await supertest(app.getHttpServer())
      .get('/v1/search?q=Hundegesetz%20Kanton%20Bern')
      .expect(200);

    expect(res.body.refusal).toMatchObject({
      code: 'jurisdiction_not_held',
      jurisdictions: [{ jurisdiction_id: 'jur_ch_be', iso_code: 'CH-BE', holding: 'not_held' }],
    });
    expect(res.body.results).toEqual([]);
    expect(res.body.totalResults).toBe(0);
  });

  it('carries NO refusal for a held canton — refusal is not the default', async () => {
    const res = await supertest(app.getHttpServer())
      .get('/v1/search?q=Statistikgesetz%20Kanton%20Z%C3%BCrich')
      .expect(200);

    expect(res.body.refusal).toBeUndefined();
    expect(res.body.results.length).toBeGreaterThan(0);
  });

  it('returns 400 when page is below minimum', async () => {
    await supertest(app.getHttpServer()).get('/v1/search?q=test&page=0').expect(400);
  });

  it('returns 400 when page_size exceeds maximum', async () => {
    await supertest(app.getHttpServer()).get('/v1/search?q=test&page_size=101').expect(400);
  });
});

// ─── Search Context ───

describe('GET /v1/search/context', () => {
  it('returns 200 with context arrays', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/search/context').expect(200);

    expect(res.body).toHaveProperty('jurisdictions');
    expect(res.body).toHaveProperty('languages');
    expect(res.body).toHaveProperty('sourceTypes');
    expect(Array.isArray(res.body.jurisdictions)).toBe(true);
    expect(Array.isArray(res.body.languages)).toBe(true);
    expect(Array.isArray(res.body.sourceTypes)).toBe(true);
  });
});

// ─── Documents ───

describe('GET /v1/documents/:id', () => {
  it('returns 200 for existing document', async () => {
    const res = await supertest(app.getHttpServer()).get('/v1/documents/doc_001').expect(200);

    expect(res.body).toHaveProperty('id');
    expect(res.body).toHaveProperty('title');
    expect(res.body).toHaveProperty('type');
  });
});

describe('GET /v1/documents/:id/sections', () => {
  it('returns 200 with data array', async () => {
    const res = await supertest(app.getHttpServer())
      .get('/v1/documents/doc_001/sections')
      .expect(200);

    expect(res.body).toHaveProperty('data');
    expect(Array.isArray(res.body.data)).toBe(true);
  });
});
