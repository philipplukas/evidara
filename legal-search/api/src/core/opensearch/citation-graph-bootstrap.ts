/**
 * Idempotent bootstrap for the two citation-graph indices, `citations` and
 * `citation-targets`.
 *
 * Why this exists: `citation-targets` was configured (`opensearch.config.ts`)
 * and had a writer (`bulkIndexCitationTargets`) but was never created on any
 * cluster, because nothing ever produced a target to write. An index that only
 * springs into existence on first write gets whatever mapping OpenSearch
 * guesses — the same class of gap #529 closed for `documents`. Creating both
 * up front, from the canonical mapping SoT, makes the graph's shape a
 * deliberate decision rather than a side effect of whichever document happened
 * to land first.
 *
 * Neither index is aliased: unlike `documents` they are written and read
 * directly, so there is no read/write alias split to keep consistent — only
 * "exists, with the right mapping".
 *
 * fetch-based (no OpenSearch client dependency), matching
 * `documents-bootstrap.ts`, so the same code runs from the API runtime
 * (`main.ts`), a seed script, or an ad-hoc deploy step.
 */

import {
  citationsIndexDefinition,
  citationTargetsIndexDefinition,
} from './citation-graph-index.mapping';

export interface CitationGraphBootstrapLogger {
  info: (message: string) => void;
  warn: (message: string) => void;
}

export interface CitationGraphBootstrapOptions {
  node: string;
  citationsIndex: string;
  citationTargetsIndex: string;
  /** Optional `Authorization` header value for secured clusters. */
  authHeader?: string;
  /** Replica count for a freshly-created index (default 0, single node). */
  numberOfReplicas?: number;
  logger?: CitationGraphBootstrapLogger;
}

export type IndexBootstrapStatus = 'exists' | 'created';

export type CitationGraphBootstrapResult = {
  citations: IndexBootstrapStatus;
  citationTargets: IndexBootstrapStatus;
};

const noopLogger: CitationGraphBootstrapLogger = { info: () => {}, warn: () => {} };

function headers(authHeader?: string): Record<string, string> {
  const base: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authHeader) base.Authorization = authHeader;
  return base;
}

async function indexExists(node: string, index: string, authHeader?: string): Promise<boolean> {
  const response = await fetch(`${node}/${index}`, {
    method: 'HEAD',
    headers: headers(authHeader),
  });
  return response.ok;
}

/**
 * Create `index` with `body` unless it already exists.
 *
 * Never mutates an existing index: the live `citations` index already holds
 * rows under a dynamic mapping, and a PUT mapping over it could conflict. An
 * existing index is left exactly as-is — the query shapes in the traversal
 * adapter are written to work against both.
 */
async function ensureIndex(
  node: string,
  index: string,
  body: Record<string, unknown>,
  authHeader: string | undefined,
  logger: CitationGraphBootstrapLogger,
): Promise<IndexBootstrapStatus> {
  if (await indexExists(node, index, authHeader)) {
    logger.info(`index ${index} already exists`);
    return 'exists';
  }

  const response = await fetch(`${node}/${index}`, {
    method: 'PUT',
    headers: headers(authHeader),
    body: JSON.stringify(body),
  });

  if (response.ok) {
    logger.info(`created index ${index}`);
    return 'created';
  }

  const text = await response.text();
  // Concurrent bootstrap (multiple API replicas raced us) — index is there.
  if (text.includes('resource_already_exists_exception')) {
    logger.info(`index ${index} created concurrently`);
    return 'exists';
  }
  throw new Error(`failed creating index ${index}: ${response.status} ${text}`);
}

/**
 * Ensure both citation-graph indices exist with the canonical mapping.
 *
 * Idempotent and non-destructive. Safe to run on every pod start.
 */
export async function bootstrapCitationGraphIndices(
  options: CitationGraphBootstrapOptions,
): Promise<CitationGraphBootstrapResult> {
  const logger = options.logger ?? noopLogger;
  const replicas = options.numberOfReplicas ?? 0;

  const citations = await ensureIndex(
    options.node,
    options.citationsIndex,
    citationsIndexDefinition(replicas),
    options.authHeader,
    logger,
  );
  const citationTargets = await ensureIndex(
    options.node,
    options.citationTargetsIndex,
    citationTargetsIndexDefinition(replicas),
    options.authHeader,
    logger,
  );

  return { citations, citationTargets };
}
