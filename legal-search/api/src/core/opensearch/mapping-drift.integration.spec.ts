/**
 * The CI-runnable half of the mapping drift guard (#675).
 *
 * `check-opensearch-mapping-drift.ts` points the same comparison at a real
 * cluster, which CI cannot reach. This spec closes the loop that CI *can*
 * verify, and it is the specific test that would have prevented the wrong
 * diagnosis of #675:
 *
 *   1. The real production creation path (`bootstrapDocumentsIndex`, what
 *      `main.ts` runs on startup) must produce an index with ZERO drift from
 *      the canonical mapping. If someone changes the mapping and forgets a
 *      producer, this goes red.
 *   2. The drift detector must actually FLAG the shape the live index had.
 *      A detector that reports "no drift" on a drifted index is worse than
 *      none, because it launders the drift as canonical.
 *
 * #675 was first "fixed" by changing the aggregations to bare field names so
 * they would resolve against the drifted index. That made the code match the
 * drift and would have broken facets against any correctly-created index. The
 * asymmetry these two tests encode — creation must be canonical, drift must be
 * reported as drift — is what makes that fix impossible to reach for.
 */
import { GenericContainer, type StartedTestContainer, Wait } from 'testcontainers';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { bootstrapDocumentsIndex } from './documents-bootstrap';
import { DOCUMENTS_INDEX_PROPERTIES } from './documents-index.mapping';
import { findMappingDrift } from './mapping-drift';

const OPENSEARCH_IMAGE = 'opensearchproject/opensearch:2.17.1';

/**
 * The mapping `scripts/validate-tar89-metadata-local.sh` used to PUT, verbatim
 * as it stood before this PR. Kept as a fixture — not as a supported shape —
 * so the detector is proven against the real historical drift rather than a
 * synthetic one. Note the bare `keyword` facet fields and the total absence of
 * `jurisdiction_ids` / `authority_ids`.
 */
const DRIFTED_LEGACY_MAPPING = {
  document_id: { type: 'keyword' },
  title: { type: 'text', analyzer: 'legal_text', fields: { keyword: { type: 'keyword' } } },
  jurisdiction: { type: 'keyword' },
  document_type: { type: 'keyword' },
  language: { type: 'keyword' },
  effective_date: { type: 'date', format: 'yyyy-MM-dd' },
  structural_path: { type: 'text' },
  content: { type: 'text', analyzer: 'legal_text' },
  content_preview: { type: 'text' },
  sections_count: { type: 'integer' },
  citations_count: { type: 'integer' },
  related_decisions_count: { type: 'integer' },
  related_commentary_count: { type: 'integer' },
  source_id: { type: 'keyword' },
  processed_at: { type: 'date' },
  authority_name: { type: 'keyword' },
  official_citation: { type: 'keyword' },
  is_official: { type: 'boolean' },
  lifecycle_status: { type: 'keyword' },
};

const LEGAL_TEXT_ANALYSIS = {
  analyzer: {
    legal_text: {
      type: 'custom',
      tokenizer: 'standard',
      filter: ['lowercase', 'german_normalization'],
    },
  },
};

let container: StartedTestContainer;
let node: string;

beforeAll(async () => {
  container = await new GenericContainer(OPENSEARCH_IMAGE)
    .withExposedPorts(9200)
    .withEnvironment({
      'discovery.type': 'single-node',
      DISABLE_SECURITY_PLUGIN: 'true',
      DISABLE_INSTALL_DEMO_CONFIG: 'true',
      OPENSEARCH_JAVA_OPTS: '-Xms512m -Xmx512m',
    })
    .withWaitStrategy(Wait.forHttp('/_cluster/health', 9200).forStatusCode(200))
    .withStartupTimeout(180_000)
    .start();
  node = `http://${container.getHost()}:${container.getMappedPort(9200)}`;
}, 240_000);

afterAll(async () => {
  await container?.stop();
});

async function liveProperties(index: string): Promise<Record<string, unknown>> {
  const response = await fetch(`${node}/${index}/_mapping`);
  const body = (await response.json()) as Record<
    string,
    { mappings?: { properties?: Record<string, unknown> } }
  >;
  const physical = Object.keys(body)[0];
  return body[physical]?.mappings?.properties ?? {};
}

const canonical = DOCUMENTS_INDEX_PROPERTIES as unknown as Record<string, unknown>;

describe('documents index mapping drift', () => {
  it('the real bootstrap path creates an index with zero drift from canonical', async () => {
    const result = await bootstrapDocumentsIndex({
      node,
      readAlias: 'drift-check-read',
      writeAlias: 'drift-check-write',
    });
    expect(result.status).toBe('created');

    const drift = findMappingDrift(await liveProperties('drift-check-read'), canonical);
    expect(drift).toEqual([]);
  }, 120_000);

  it('flags the drifted mapping the live index actually had', async () => {
    await fetch(`${node}/drifted-documents`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        settings: { number_of_shards: 1, number_of_replicas: 0, analysis: LEGAL_TEXT_ANALYSIS },
        mappings: { properties: DRIFTED_LEGACY_MAPPING },
      }),
    });

    const drift = findMappingDrift(await liveProperties('drifted-documents'), canonical);
    const byField = new Map(drift.map((finding) => [finding.field, finding.kind]));

    // The #675 case proper: the aggregation targets are missing.
    expect(byField.get('jurisdiction.keyword')).toBe('missing-subfield');
    expect(byField.get('document_type.keyword')).toBe('missing-subfield');
    expect(byField.get('language.keyword')).toBe('missing-subfield');

    // And the finding originally filed as a separate projection/backfill gap:
    // `authority_ids` is absent for exactly the same reason — the mapping that
    // created the index never declared it.
    expect(byField.get('authority_ids')).toBe('missing-field');
    expect(byField.get('jurisdiction_ids')).toBe('missing-field');
  }, 120_000);
});
