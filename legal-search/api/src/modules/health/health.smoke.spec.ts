/**
 * Smoke tests — HTTP-level confidence that the app boots and core endpoints respond.
 *
 * These run against the real running app (not a mock context).
 * Run with: npm run test:smoke
 *
 * Note: These tests require the app to be running on localhost:3001.
 * In CI, start the app before running smoke tests.
 */
const BASE_URL = process.env.API_URL ?? 'http://localhost:3001';

describe('App smoke tests', () => {
  it('GET /health → 200 with status ok', async () => {
    const res = await fetch(`${BASE_URL}/health`);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { status: string };
    expect(body.status).toBe('ok');
  });

  it('GET /api → Swagger UI loads (non-production only)', async () => {
    const res = await fetch(`${BASE_URL}/api`);
    if (process.env.NODE_ENV === 'production') {
      // Swagger is disabled in production
      expect(res.status).toBe(404);
    } else {
      expect(res.status).toBe(200);
    }
  });

  it('GET /v1/search?q=test → 200 (requires running OpenSearch)', async () => {
    const res = await fetch(`${BASE_URL}/v1/search?q=test`);
    // 200 with empty results is fine — this just confirms the endpoint is wired
    // 503 is acceptable if OpenSearch is not running in this environment
    expect([200, 503]).toContain(res.status);
  });
});
