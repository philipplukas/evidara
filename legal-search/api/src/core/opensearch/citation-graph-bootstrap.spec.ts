import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { bootstrapCitationGraphIndices } from './citation-graph-bootstrap';

const NODE = 'http://opensearch:9200';

function respond(status: number, body = '{}'): Response {
  return new Response(body, { status });
}

describe('bootstrapCitationGraphIndices', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('creates both indices when neither exists', async () => {
    // HEAD (miss) + PUT, twice.
    fetchMock
      .mockResolvedValueOnce(respond(404))
      .mockResolvedValueOnce(respond(200))
      .mockResolvedValueOnce(respond(404))
      .mockResolvedValueOnce(respond(200));

    const result = await bootstrapCitationGraphIndices({
      node: NODE,
      citationsIndex: 'citations',
      citationTargetsIndex: 'citation-targets',
    });

    expect(result).toEqual({ citations: 'created', citationTargets: 'created' });

    const puts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'PUT');
    expect(puts).toHaveLength(2);
    expect(puts[1][0]).toBe(`${NODE}/citation-targets`);
    // The mapping must actually be sent — an index created without one is the
    // gap this bootstrap exists to close.
    const body = JSON.parse(puts[1][1].body as string);
    expect(body.mappings.properties.identifier_value.type).toBe('keyword');
  });

  it('leaves an existing index untouched', async () => {
    // The live `citations` index already holds rows under a dynamic mapping;
    // a PUT over it could conflict, so it must never be rewritten.
    fetchMock
      .mockResolvedValueOnce(respond(200)) // citations HEAD -> exists
      .mockResolvedValueOnce(respond(404)) // citation-targets HEAD -> miss
      .mockResolvedValueOnce(respond(200)); // citation-targets PUT

    const result = await bootstrapCitationGraphIndices({
      node: NODE,
      citationsIndex: 'citations',
      citationTargetsIndex: 'citation-targets',
    });

    expect(result).toEqual({ citations: 'exists', citationTargets: 'created' });
    const puts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'PUT');
    expect(puts).toHaveLength(1);
    expect(puts[0][0]).toBe(`${NODE}/citation-targets`);
  });

  it('tolerates a concurrent bootstrap from another replica', async () => {
    fetchMock
      .mockResolvedValueOnce(respond(404))
      .mockResolvedValueOnce(respond(400, '{"error":{"type":"resource_already_exists_exception"}}'))
      .mockResolvedValueOnce(respond(200));

    const result = await bootstrapCitationGraphIndices({
      node: NODE,
      citationsIndex: 'citations',
      citationTargetsIndex: 'citation-targets',
    });

    expect(result).toEqual({ citations: 'exists', citationTargets: 'exists' });
  });

  it('throws on a genuine create failure', async () => {
    fetchMock.mockResolvedValueOnce(respond(404)).mockResolvedValueOnce(respond(500, 'boom'));

    await expect(
      bootstrapCitationGraphIndices({
        node: NODE,
        citationsIndex: 'citations',
        citationTargetsIndex: 'citation-targets',
      }),
    ).rejects.toThrow(/failed creating index citations/);
  });
});
