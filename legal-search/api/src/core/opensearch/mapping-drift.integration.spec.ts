/**
 * The CI-runnable half of the mapping drift guard (#675).
 *
 * `check-opensearch-mapping-drift.ts` points the same comparison at a real
 * cluster, which CI cannot reach. This spec closes the loop that CI *can*
 * verify, and it is the specific test that would have prevented the wrong
 * diagnosis of #675:
 *
 *   1. EVERY production creation path — enumerated in `PRODUCERS` below — must
 *      produce an index with ZERO drift from the canonical mapping, and with
 *      the `legal_text` analyzer present. If someone changes the mapping and
 *      forgets a producer, this goes red.
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
import {
  bootstrapDocumentsIndex,
  CUTOVER_REPLICAS,
  createDocumentsIndex,
} from './documents-bootstrap';
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

/**
 * Every code path that may CREATE a documents index, enumerated (#713).
 *
 * This registry is the guard's whole point. It previously tested only
 * `bootstrapDocumentsIndex`, which left `opensearch-alias-cutover.ts` creating
 * indices with no integration coverage at all, and said nothing about the GCP
 * runtime tfvars job that created one with no mapping whatsoever — the #713
 * defect. That job is gone and its creation duty now belongs to the startup
 * bootstrap, so the two entries below are the complete set.
 *
 * If you add a producer, add it here. If you cannot add it here — because it
 * PUTs a mapping of its own instead of calling `createDocumentsIndex` — that
 * is the defect, not the test.
 */
const PRODUCERS: Array<{ name: string; index: string; create: (index: string) => Promise<void> }> =
  [
    {
      name: 'startup bootstrap (main.ts → bootstrapDocumentsIndex)',
      index: 'drift-check-read',
      create: async () => {
        const result = await bootstrapDocumentsIndex({
          node,
          readAlias: 'drift-check-read',
          writeAlias: 'drift-check-write',
        });
        expect(result.status).toBe('created');
      },
    },
    {
      name: 'versioned cutover (scripts/opensearch-alias-cutover.ts → ensureIndex)',
      index: 'drift-check-cutover',
      // Mirrors that script's `ensureIndex` exactly: the shared creator, cutover
      // replica count, no tolerance for a colliding name.
      create: (index) => createDocumentsIndex(node, index, { numberOfReplicas: CUTOVER_REPLICAS }),
    },
  ];

describe('documents index mapping drift', () => {
  it.each(PRODUCERS)('producer "$name" creates an index with zero drift from canonical', async ({
    index,
    create,
  }) => {
    await create(index);
    const drift = findMappingDrift(await liveProperties(index), canonical);
    expect(drift).toEqual([]);
  }, 120_000);

  it('every producer creates the legal_text analyzer', async () => {
    // #713: the removed GCP job PUT settings with no `analysis` block, so
    // `legal_text` did not exist and German normalization silently never
    // applied — Straße/Strasse stopped matching. A missing analyzer is a
    // recall loss the property-level drift check above cannot see.
    for (const { index } of PRODUCERS) {
      const response = await fetch(`${node}/${index}/_settings`);
      const body = (await response.json()) as Record<
        string,
        { settings?: { index?: { analysis?: { analyzer?: Record<string, unknown> } } } }
      >;
      const physical = Object.keys(body)[0];
      const analyzers = body[physical]?.settings?.index?.analysis?.analyzer ?? {};
      expect(Object.keys(analyzers), `${index} is missing legal_text`).toContain('legal_text');
    }
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
