import type { ConfigService } from '@nestjs/config';
import { describe, expect, it, vi } from 'vitest';
import type { MetricsService } from '../../core/metrics/metrics.service';
import { ProjectionOpenSearchAdapter } from './opensearch.adapter';

/**
 * `listIndexedDocuments` is the index side of the ADR-0005 reconcile diff, and every
 * failure mode it has is silent-by-default: a wrong sort field, a swallowed error, or a
 * missing exclusion all produce a plausible-looking page that makes a reconcile pass
 * delete the wrong documents (or miss the orphans entirely). So the query shape is
 * asserted literally, not just the returned rows.
 */
function makeAdapter(search: ReturnType<typeof vi.fn>) {
  return new ProjectionOpenSearchAdapter(
    { search } as never,
    {
      get: (key: string) =>
        key === 'opensearch.documentsWriteAlias' ? 'documents-write-test' : null,
    } as ConfigService,
    { recordDocumentIndexed: vi.fn(), recordDocumentDeleted: vi.fn() } as unknown as MetricsService,
  );
}

const page = (sources: Record<string, unknown>[]) => ({
  body: { hits: { hits: sources.map((_source) => ({ _source })) } },
});

describe('ProjectionOpenSearchAdapter.listIndexedDocuments', () => {
  it('walks the write alias in document_id order and returns projection provenance', async () => {
    const search = vi.fn().mockResolvedValue(
      page([
        {
          document_id: 'doc_01jq7bdptzqv3xs0c41xpw1yba',
          document_revision: 2,
          processing_manifest_id: 'pm_01jq7bhgy7g0pkj4f1d03f8f8c',
          source_id: 'src_01jq7bdptzqv3xs0c41xpw1ybg',
          source_version_id: 'sv_01jq7bdptzqv3xs0c41xpw1ybg',
          run_id: 'run_01jq7bdptzqv3xs0c41xpw1ybg',
          title: 'Bundesverfassung',
        },
      ]),
    );

    const result = await makeAdapter(search).listIndexedDocuments({ limit: 2 });

    const [{ index, body }] = search.mock.calls[0];
    expect(index).toBe('documents-write-test');
    // `document_id` is a `keyword` in documents-index.mapping.ts — sorting on a
    // text field would throw and sorting on the wrong field breaks the cursor.
    expect(body.sort).toEqual([{ document_id: { order: 'asc' } }]);
    expect(result.data[0]).toEqual({
      document_id: 'doc_01jq7bdptzqv3xs0c41xpw1yba',
      document_revision: 2,
      processing_manifest_id: 'pm_01jq7bhgy7g0pkj4f1d03f8f8c',
      source_id: 'src_01jq7bdptzqv3xs0c41xpw1ybg',
      source_version_id: 'sv_01jq7bdptzqv3xs0c41xpw1ybg',
      run_id: 'run_01jq7bdptzqv3xs0c41xpw1ybg',
      title: 'Bundesverfassung',
    });
  });

  it('excludes commentary_insight rows, which have no canonical document behind them', async () => {
    const search = vi.fn().mockResolvedValue(page([]));

    await makeAdapter(search).listIndexedDocuments({});

    const [{ body }] = search.mock.calls[0];
    expect(body.query.bool.must_not).toEqual([{ term: { record_kind: 'commentary_insight' } }]);
  });

  it('pages with search_after and stops the cursor on a short page', async () => {
    const full = vi
      .fn()
      .mockResolvedValue(page([{ document_id: 'doc_a' }, { document_id: 'doc_b' }]));
    const short = vi.fn().mockResolvedValue(page([{ document_id: 'doc_c' }]));

    const first = await makeAdapter(full).listIndexedDocuments({ limit: 2 });
    expect(first.next_after).toBe('doc_b');

    const second = await makeAdapter(short).listIndexedDocuments({ after: 'doc_b', limit: 2 });
    expect(short.mock.calls[0][0].body.search_after).toEqual(['doc_b']);
    // A short page is the end of the walk; emitting a cursor here would loop forever.
    expect(second.next_after).toBeUndefined();
  });

  it('propagates a failed search instead of reporting an empty index', async () => {
    // The dangerous silent failure: an empty result reads as "nothing is indexed",
    // which tells a reconcile pass that nothing is orphaned.
    const search = vi.fn().mockRejectedValue(new Error('connection refused'));

    await expect(makeAdapter(search).listIndexedDocuments({})).rejects.toThrow(
      'connection refused',
    );
  });

  it('reports an absent index as an empty page, which is the honest answer', async () => {
    const search = vi.fn().mockRejectedValue(new Error('index_not_found_exception'));

    await expect(makeAdapter(search).listIndexedDocuments({})).resolves.toEqual({
      data: [],
      limit: 500,
    });
  });
});

/**
 * The candidate lookup is where ambiguity is either preserved or destroyed. It
 * used to return `Map<key, match>` and let the LAST hit win, and it used to
 * page `size: normalizedRefs.length` — one row per key — which truncates the
 * rival rows an ambiguity refusal is computed from. Both defects are invisible
 * downstream: the caller just sees a single confident match.
 */
describe('ProjectionOpenSearchAdapter.resolveCitationTargets', () => {
  it('returns EVERY row a key matched, so ambiguity survives the lookup', async () => {
    const search = vi.fn().mockResolvedValue(
      page([
        { document_id: 'doc_zh', identifier_type: 'abbrev_art', identifier_value: 'EG/1' },
        { document_id: 'doc_be', identifier_type: 'abbrev_art', identifier_value: 'EG/1' },
      ]),
    );

    const result = await makeAdapter(search).resolveCitationTargets(['abbrev_art:EG/1']);

    expect(result.get('abbrev_art:EG/1')?.map((t) => t.document_id)).toEqual(['doc_zh', 'doc_be']);
  });

  it('requests more rows than there are keys', async () => {
    const search = vi.fn().mockResolvedValue(page([]));

    await makeAdapter(search).resolveCitationTargets(['sr:210', 'sr:220']);

    const [{ body }] = search.mock.calls[0];
    // A page sized to the key count can only ever return one row per key, which
    // makes every ambiguous key look unique.
    expect(body.size).toBeGreaterThan(2);
  });

  it('carries the section fields, so a provision-level target stays provision-level', async () => {
    const search = vi.fn().mockResolvedValue(
      page([
        {
          document_id: 'doc_bv',
          identifier_type: 'abbrev_art',
          identifier_value: 'BV/36',
          section_id: 'sec_36',
          section_anchor: 'art_36',
        },
      ]),
    );

    const result = await makeAdapter(search).resolveCitationTargets(['abbrev_art:BV/36']);

    expect(result.get('abbrev_art:BV/36')?.[0]).toMatchObject({
      section_id: 'sec_36',
      section_anchor: 'art_36',
    });
  });
});
