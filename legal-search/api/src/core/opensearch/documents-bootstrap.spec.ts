import { afterEach, describe, expect, it, vi } from 'vitest';
import { bootstrapDocumentsIndex } from './documents-bootstrap';

type Handler = (url: string, method: string) => Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function installFetch(handler: Handler): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    const method = (init?.method ?? 'GET').toUpperCase();
    return handler(url, method);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const OPTS = {
  node: 'http://os:9200',
  readAlias: 'documents-read',
  writeAlias: 'documents-write',
};

function bodyOf(call: unknown[]): Record<string, unknown> {
  return JSON.parse((call[1] as RequestInit).body as string);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('bootstrapDocumentsIndex', () => {
  it('creates the physical index + both aliases when the read alias is absent', async () => {
    const fetchMock = installFetch((url, method) => {
      if (method === 'GET' && url.endsWith('/_alias/documents-read')) {
        return new Response('', { status: 404 });
      }
      if (method === 'HEAD' && url.endsWith('/documents-000001')) {
        return new Response('', { status: 404 });
      }
      if (method === 'PUT' && url.endsWith('/documents-000001')) {
        return jsonResponse(200, { acknowledged: true });
      }
      if (method === 'GET' && url.endsWith('/_alias/documents-write')) {
        return new Response('', { status: 404 });
      }
      if (method === 'POST' && url.endsWith('/_aliases')) {
        return jsonResponse(200, { acknowledged: true });
      }
      throw new Error(`unexpected ${method} ${url}`);
    });

    const result = await bootstrapDocumentsIndex(OPTS);
    expect(result).toEqual({ status: 'created', physicalIndex: 'documents-000001' });

    const putCall = fetchMock.mock.calls.find(
      ([u, init]) => String(u).endsWith('/documents-000001') && init?.method === 'PUT',
    );
    expect(putCall).toBeDefined();
    const mapping = bodyOf(putCall as unknown[]);
    const settings = mapping.settings as Record<string, Record<string, Record<string, unknown>>>;
    const analyzer = settings.analysis.analyzer as Record<string, { filter: string[] }>;
    expect(analyzer.legal_text.filter).toContain('german_normalization');
    const properties = (mapping.mappings as Record<string, Record<string, { type: string }>>)
      .properties;
    expect(properties.record_kind.type).toBe('keyword');

    const aliasCall = fetchMock.mock.calls.find(
      ([u, init]) => String(u).endsWith('/_aliases') && init?.method === 'POST',
    );
    const actions = bodyOf(aliasCall as unknown[]).actions as Array<Record<string, unknown>>;
    const adds = actions
      .filter((a) => 'add' in a)
      .map((a) => (a as { add: unknown }).add);
    expect(adds).toContainEqual({ index: 'documents-000001', alias: 'documents-read' });
    expect(adds).toContainEqual({
      index: 'documents-000001',
      alias: 'documents-write',
      is_write_index: true,
    });
  });

  it('is a no-op when the read alias already resolves', async () => {
    const fetchMock = installFetch((url) => {
      if (url.endsWith('/_alias/documents-read')) {
        return jsonResponse(200, { 'documents-000001': { aliases: { 'documents-read': {} } } });
      }
      throw new Error(`should not call ${url}`);
    });

    const result = await bootstrapDocumentsIndex(OPTS);
    expect(result).toEqual({ status: 'exists', physicalIndex: 'documents-000001' });

    const mutated = fetchMock.mock.calls.some(([, init]) => (init?.method ?? 'GET') !== 'GET');
    expect(mutated).toBe(false);
  });
});
