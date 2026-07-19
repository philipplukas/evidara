#!/usr/bin/env npx tsx

/// <reference types="node" />

/**
 * Compare a LIVE documents index against the canonical mapping (#675).
 *
 * The canonical mapping in `src/core/opensearch/documents-index.mapping.ts` was
 * declared the source of truth, but nothing checked that any running index
 * matched it. Two producers had drifted from it:
 *
 *   - `scripts/validate-tar89-metadata-local.sh` (local/lean stack) carried a
 *     hand-maintained copy: bare `keyword` facet fields, no `jurisdiction_ids`,
 *     no `authority_ids`. Fixed in this PR.
 *   - `infra/env/*\/runtime.gcp.tfvars*` (GCP deploys) creates the index with
 *     SETTINGS ONLY — no mappings, no `legal_text` analyzer — so every string
 *     field falls back to dynamic `text` + `.keyword`. NOT fixed here; that is
 *     an infra change requiring a coordinated reindex per environment.
 *
 * Neither drift surfaces as an error at query time. Aggregating a field that
 * does not exist returns empty buckets; filtering a `text` field with `terms`
 * silently matches nothing. That is why this check has to be structural.
 *
 * Usage:
 *   OPENSEARCH_NODE=http://127.0.0.1:9200 npm run mapping:check-drift
 *   OPENSEARCH_NODE=... OPENSEARCH_INDEX=documents-read \
 *     OPENSEARCH_AUTH_HEADER="Basic ..." npm run mapping:check-drift
 *
 * Exits 1 on drift, 0 when the live index satisfies the canonical mapping.
 * Deliberately NOT part of `npm run check`: that gate must stay runnable with
 * no cluster reachable. The CI-runnable half of this guard is the integration
 * test, which asserts the real bootstrap path produces a drift-free index.
 */
import { DOCUMENTS_INDEX_PROPERTIES } from '../src/core/opensearch/documents-index.mapping';
import { findMappingDrift, formatMappingDrift } from '../src/core/opensearch/mapping-drift';

const node = (process.env.OPENSEARCH_NODE ?? 'http://127.0.0.1:9200').replace(/\/$/, '');
const index = process.env.OPENSEARCH_INDEX ?? process.env.OPENSEARCH_ALIAS_READ ?? 'documents-read';
const authHeader = process.env.OPENSEARCH_AUTH_HEADER;

async function main(): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authHeader) headers.Authorization = authHeader;

  const response = await fetch(`${node}/${index}/_mapping`, { headers });
  if (!response.ok) {
    console.error(`error: GET ${node}/${index}/_mapping returned ${response.status}`);
    process.exit(2);
  }

  // `_mapping` on an alias returns one entry per physical index behind it.
  // Every one of them serves queries, so every one of them must satisfy the
  // contract — a half-migrated alias is exactly the state worth catching.
  const body = (await response.json()) as Record<
    string,
    { mappings?: { properties?: Record<string, unknown> } }
  >;
  const physicalIndices = Object.keys(body);
  if (physicalIndices.length === 0) {
    console.error(`error: ${index} resolved to no physical index`);
    process.exit(2);
  }

  let drifted = false;
  for (const physical of physicalIndices) {
    const live = body[physical]?.mappings?.properties ?? {};
    const findings = findMappingDrift(
      live,
      DOCUMENTS_INDEX_PROPERTIES as unknown as Record<string, unknown>,
    );
    const label = physical === index ? physical : `${index} -> ${physical}`;
    console.log(formatMappingDrift(findings, label));
    if (findings.length > 0) drifted = true;
  }

  process.exit(drifted ? 1 : 0);
}

main().catch((err: unknown) => {
  console.error(`error: ${(err as Error).message}`);
  process.exit(2);
});
