import type { ConfigService } from '@nestjs/config';
import { describe, expect, it, vi } from 'vitest';
import { CitationsOpenSearchAdapter } from './opensearch.adapter';

/**
 * These tests pin the QUERY SHAPES, not just the return values.
 *
 * The failure they exist to catch is silent: if a term filter targets a field
 * that is not a `keyword` (or loses its `.keyword` sub-field), OpenSearch
 * happily returns zero hits and the traversal reports "nothing cites this
 * norm" — indistinguishable from a correct empty answer. That is the exact
 * class of bug that left `citation-targets` empty and unnoticed. So the field
 * names are asserted literally, against the mapping in
 * `core/opensearch/citation-graph-index.mapping.ts`.
 */
function makeAdapter(search: ReturnType<typeof vi.fn>) {
  return new CitationsOpenSearchAdapter(
    { search } as never,
    {
      get: (key: string) => {
        switch (key) {
          case 'opensearch.citationsIndex':
            return 'citations-test';
          case 'opensearch.citationTargetsIndex':
            return 'citation-targets-test';
          default:
            return null;
        }
      },
    } as ConfigService,
  );
}

const hits = (sources: Record<string, unknown>[]) => ({
  body: { hits: { hits: sources.map((_source) => ({ _source })) } },
});

describe('CitationsOpenSearchAdapter', () => {
  describe('findTargetsByKey', () => {
    it('filters citation-targets on the exact identifier, split from the key', async () => {
      const search = vi.fn().mockResolvedValue(
        hits([
          {
            document_id: 'doc_zgb',
            identifier_type: 'sr',
            identifier_value: '210',
            title: 'Schweizerisches Zivilgesetzbuch',
          },
        ]),
      );

      const targets = await makeAdapter(search).findTargetsByKey('sr:210');

      const [{ index, body }] = search.mock.calls[0];
      expect(index).toBe('citation-targets-test');
      expect(body.query.bool.filter).toEqual([
        { term: { 'identifier_type.keyword': 'sr' } },
        { term: { 'identifier_value.keyword': '210' } },
      ]);
      expect(targets[0].document_id).toBe('doc_zgb');
    });

    it('never queries for a key it cannot parse', async () => {
      const search = vi.fn();
      const targets = await makeAdapter(search).findTargetsByKey('Art. 36 BV');

      expect(search).not.toHaveBeenCalled();
      expect(targets).toEqual([]);
    });

    it('degrades to an empty graph when the index is absent', async () => {
      // Before this PR `citation-targets` did not exist on any cluster. The
      // traversal must survive that, not 500.
      const search = vi.fn().mockRejectedValue(new Error('index_not_found_exception'));
      await expect(makeAdapter(search).findTargetsByKey('sr:210')).resolves.toEqual([]);
    });
  });

  describe('findCitingEdges', () => {
    it('matches on the canonical key OR the denormalized target id', async () => {
      const search = vi.fn().mockResolvedValue(
        hits([
          {
            citation_id: 'cit_1',
            source_document_id: 'doc_bv',
            citation_text: 'SR 210',
            normalized_reference: 'sr:210',
          },
        ]),
      );

      const edges = await makeAdapter(search).findCitingEdges({
        normalizedReferences: ['sr:210'],
        documentId: 'doc_zgb',
        limit: 25,
      });

      const [{ index, body }] = search.mock.calls[0];
      expect(index).toBe('citations-test');
      expect(body.size).toBe(25);
      // The key clause is what makes the edge order-independent; the id clause
      // catches rows that were denormalized at write time. Both, OR'd.
      expect(body.query.bool.should).toEqual([
        { terms: { 'normalized_reference.keyword': ['sr:210'] } },
        { term: { 'target_document_id.keyword': 'doc_zgb' } },
      ]);
      expect(body.query.bool.minimum_should_match).toBe(1);
      expect(edges[0].source_document_id).toBe('doc_bv');
    });

    it('does not issue a match-all when there is nothing to match on', async () => {
      // A `should: []` bool query matches EVERY citation in the corpus. Returning
      // the entire index as "citing this norm" would be catastrophically wrong.
      const search = vi.fn();
      const edges = await makeAdapter(search).findCitingEdges({
        normalizedReferences: [],
        limit: 10,
      });

      expect(search).not.toHaveBeenCalled();
      expect(edges).toEqual([]);
    });
  });

  describe('getResolutionStats', () => {
    it('counts an edge as resolved only when its key is a real target', async () => {
      const search = vi
        .fn()
        // 1st call: loadAllTargetKeys over citation-targets.
        .mockResolvedValueOnce({
          body: {
            aggregations: {
              by_type: {
                buckets: [{ key: 'sr', by_value: { buckets: [{ key: '101' }, { key: '210' }] } }],
              },
            },
          },
        })
        // 2nd call: the citations aggregation.
        .mockResolvedValueOnce({
          body: {
            hits: { total: { value: 10 } },
            aggregations: {
              with_key: {
                doc_count: 4,
                by_key: {
                  buckets: [
                    { key: 'sr:210', doc_count: 2 }, // in corpus -> resolved
                    { key: 'sr:101', doc_count: 1 }, // in corpus -> resolved
                    { key: 'sr:999', doc_count: 1 }, // dangling -> NOT resolved
                  ],
                },
              },
              unresolved_by_type: {
                by_type: { buckets: [{ key: 'article', doc_count: 6 }] },
              },
            },
          },
        });

      const stats = await makeAdapter(search).getResolutionStats();

      expect(stats.total).toBe(10);
      expect(stats.withNormalizedReference).toBe(4);
      expect(stats.resolvable).toBe(3);
      // sr:999 has a perfectly valid key but addresses no norm we hold. It is a
      // BROKEN EDGE, and it must not quietly count as resolved.
      expect(stats.unresolvedByType).toEqual({ unresolved_target: 1, article: 6 });
    });
  });
});

describe('CitationsOpenSearchAdapter.findTargetsByKeys (the read-time batch join)', () => {
  it('groups every row per key and pages above one row per key', async () => {
    const search = vi.fn().mockResolvedValue(
      hits([
        { document_id: 'doc_zh', identifier_type: 'abbrev_art', identifier_value: 'EG/1' },
        { document_id: 'doc_be', identifier_type: 'abbrev_art', identifier_value: 'EG/1' },
        { document_id: 'doc_bv', identifier_type: 'sr', identifier_value: '101' },
      ]),
    );

    const result = await makeAdapter(search).findTargetsByKeys(['abbrev_art:EG/1', 'sr:101']);

    expect(result.get('abbrev_art:EG/1')?.map((t) => t.document_id)).toEqual(['doc_zh', 'doc_be']);
    expect(result.get('sr:101')?.map((t) => t.document_id)).toEqual(['doc_bv']);
    const [{ index, body }] = search.mock.calls[0];
    expect(index).toBe('citation-targets-test');
    expect(body.size).toBeGreaterThan(2);
  });

  it('does not query at all when no key parses', async () => {
    const search = vi.fn();
    const result = await makeAdapter(search).findTargetsByKeys(['not-a-key']);
    expect(search).not.toHaveBeenCalled();
    expect(result.size).toBe(0);
  });

  // UNKNOWN must reach the caller. Swallowing the error here would make an
  // OpenSearch outage read as "the corpus holds no such norm".
  it('rejects when the lookup fails instead of returning an empty map', async () => {
    const search = vi.fn().mockRejectedValue(new Error('connection refused'));
    await expect(makeAdapter(search).findTargetsByKeys(['sr:101'])).rejects.toThrow(
      'connection refused',
    );
  });
});
