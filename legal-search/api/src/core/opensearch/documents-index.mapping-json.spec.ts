/**
 * Drift gate for the generated JSON copy of the canonical mapping (#675).
 *
 * `scripts/validate-tar89-metadata-local.sh` PUTs this file to create the
 * documents index. If it is allowed to fall behind the TypeScript source of
 * truth, the exact failure #675 came from reappears — an index whose facet
 * fields lack the `.keyword` sub-fields the aggregations target, returning
 * empty buckets rather than an error.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { renderDocumentsIndexMappingJson } from './documents-index.mapping-json';

const MAPPING_JSON_PATH = resolve(
  __dirname,
  '../../../../../scripts/opensearch/documents-index.mapping.json',
);

describe('generated documents-index mapping JSON', () => {
  it('matches the canonical TypeScript definition byte for byte', () => {
    const committed = readFileSync(MAPPING_JSON_PATH, 'utf8');
    expect(committed).toBe(renderDocumentsIndexMappingJson());
  });

  it('declares the `.keyword` sub-fields the facet aggregations target', () => {
    const parsed = JSON.parse(readFileSync(MAPPING_JSON_PATH, 'utf8')) as {
      mappings: { properties: Record<string, { fields?: Record<string, unknown> }> };
    };
    // These three are what the search aggregations bucket on. The drifted
    // shell-script mapping declared them as bare `keyword`, which is why the
    // filter rail was dead.
    for (const field of ['jurisdiction', 'document_type', 'language']) {
      expect(parsed.mappings.properties[field]?.fields?.keyword).toBeDefined();
    }
  });

  it('declares the projection-only ID fields the drifted mapping omitted', () => {
    const parsed = JSON.parse(readFileSync(MAPPING_JSON_PATH, 'utf8')) as {
      mappings: { properties: Record<string, unknown> };
    };
    // `authority_ids` being absent from the deployed index — the finding
    // originally filed as a projection/backfill gap — is this same omission.
    expect(parsed.mappings.properties.authority_ids).toBeDefined();
    expect(parsed.mappings.properties.jurisdiction_ids).toBeDefined();
  });
});
