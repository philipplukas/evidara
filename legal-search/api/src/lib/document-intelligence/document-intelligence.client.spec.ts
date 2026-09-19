import type { ConfigService } from '@nestjs/config';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  HttpDocumentIntelligenceClient,
  LeanDocumentUnavailableError,
} from './document-intelligence.client';

/**
 * The whole point of this file is that a 404 and a 5xx do NOT produce the same
 * caller-visible outcome (#984). An assertion both satisfy — "returns falsy",
 * "logs a warning", "does not throw a TypeError" — is the defect written down
 * as a test, so every case here pins one specific outcome and the last test
 * asserts the two differ.
 *
 * These drive the real mutator over a stubbed `fetch`, because the split
 * between "absent" and "failed" is made partly in the mutator (404 is returned
 * as data, everything else non-ok throws) and partly in the client. Mocking the
 * generated call would test only half the hop.
 */

const BASE_URL = 'http://document-intelligence.test';

function makeClient(baseUrl: string = BASE_URL): HttpDocumentIntelligenceClient {
  const config = {
    get: (key: string) => (key === 'documentIntelligence.baseUrl' ? baseUrl : undefined),
  } as unknown as ConfigService;
  return new HttpDocumentIntelligenceClient(config);
}

function respondWith(status: number, body: unknown, contentType = 'application/json'): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          // 204 is a null-body status; `new Response('', {status: 204})` throws.
          status === 204 ? null : typeof body === 'string' ? body : JSON.stringify(body),
          { status, headers: { 'content-type': contentType } },
        ),
    ),
  );
}

describe('HttpDocumentIntelligenceClient.fetchLeanDocument', () => {
  beforeEach(() => {
    // `vi.stubEnv` rather than assigning `process.env` directly: `noProcessEnv`
    // is an error in this surface outside `src/core/config/**`.
    vi.stubEnv('DOCUMENT_INTELLIGENCE_BASE_URL', BASE_URL);
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('returns the payload on 200', async () => {
    respondWith(200, { document_id: 'doc_1', body_text: 'Art. 1' });

    await expect(makeClient().fetchLeanDocument('doc_1')).resolves.toEqual({
      document_id: 'doc_1',
      body_text: 'Art. 1',
    });
  });

  it('returns null on 404 — the upstream says there is no canonical row', async () => {
    respondWith(404, { detail: 'not found' });

    await expect(makeClient().fetchLeanDocument('doc_missing')).resolves.toBeNull();
  });

  it('throws on 503 rather than returning null — #983 issues that refusal on purpose', async () => {
    respondWith(503, { detail: 'published sections unavailable' });

    const error = await makeClient()
      .fetchLeanDocument('doc_1')
      .then(
        (value) => {
          throw new Error(`expected a refusal, got ${JSON.stringify(value)}`);
        },
        (err: unknown) => err,
      );

    expect(error).toBeInstanceOf(LeanDocumentUnavailableError);
    expect((error as LeanDocumentUnavailableError).status).toBe(503);
    expect((error as LeanDocumentUnavailableError).documentId).toBe('doc_1');
  });

  it('throws on 500', async () => {
    respondWith(500, { detail: 'boom' });

    await expect(makeClient().fetchLeanDocument('doc_1')).rejects.toBeInstanceOf(
      LeanDocumentUnavailableError,
    );
  });

  it('throws with status null on a transport failure — no answer is not an absence', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );

    const error = await makeClient()
      .fetchLeanDocument('doc_1')
      .then(
        () => {
          throw new Error('expected a refusal');
        },
        (err: unknown) => err,
      );

    expect(error).toBeInstanceOf(LeanDocumentUnavailableError);
    expect((error as LeanDocumentUnavailableError).status).toBeNull();
  });

  it('throws on an unexpected 2xx rather than reading it as absence', async () => {
    // A 204 used to fall through the `status === 200` check and return null,
    // asserting "no canonical row" on the strength of a status we do not model.
    respondWith(204, null);

    await expect(makeClient().fetchLeanDocument('doc_1')).rejects.toBeInstanceOf(
      LeanDocumentUnavailableError,
    );
  });

  it('returns null when the integration is switched off, without calling fetch', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    await expect(makeClient('').fetchLeanDocument('doc_1')).resolves.toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('gives 404 and 503 different outcomes — the one assertion #984 is about', async () => {
    // Stated as a single comparison on purpose. Every other test in this file
    // would still pass if the client returned null for both; this one is the
    // test that goes red when the distinction is removed.
    respondWith(404, { detail: 'not found' });
    const onNotFound = await makeClient()
      .fetchLeanDocument('doc_1')
      .then(
        (value) => ({ kind: 'resolved' as const, value }),
        (err: unknown) => ({ kind: 'rejected' as const, err }),
      );

    respondWith(503, { detail: 'unavailable' });
    const onUnavailable = await makeClient()
      .fetchLeanDocument('doc_1')
      .then(
        (value) => ({ kind: 'resolved' as const, value }),
        (err: unknown) => ({ kind: 'rejected' as const, err }),
      );

    expect(onNotFound.kind).not.toBe(onUnavailable.kind);
    expect(onNotFound).toEqual({ kind: 'resolved', value: null });
    expect(onUnavailable.kind).toBe('rejected');
  });
});
