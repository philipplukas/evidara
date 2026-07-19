/**
 * Idempotent bootstrap for the legal-search `documents` index and its
 * read/write aliases.
 *
 * The core invariant this guarantees: the `documents-read` alias (what
 * search queries) and the `documents-write` alias (what projections
 * write) BOTH resolve to the same physical index. When they don't, a
 * projected document lands in the write index but never surfaces in
 * search — the single most likely place a document "disappears".
 *
 * fetch-based (no OpenSearch client dependency) so the same code runs
 * from the API runtime (`main.ts`), the local seed script, and any
 * ad-hoc deploy step.
 */

import { documentsIndexDefinition } from './documents-index.mapping';

export interface BootstrapLogger {
  info: (message: string) => void;
  warn: (message: string) => void;
}

export interface BootstrapOptions {
  node: string;
  readAlias: string;
  writeAlias: string;
  /** Optional `Authorization` header value for secured clusters. */
  authHeader?: string;
  /** Replica count for a freshly-created index (default 0, single node). */
  numberOfReplicas?: number;
  logger?: BootstrapLogger;
}

export type BootstrapResult = {
  status: 'exists' | 'created';
  physicalIndex: string;
};

const noopLogger: BootstrapLogger = { info: () => {}, warn: () => {} };

/**
 * Derive the physical index name that both aliases will point at.
 * `documents-read` → `documents-000001`; a read alias without the
 * `-read` suffix gets `-000001` appended.
 */
export function deriveDocumentsPhysicalIndex(readAlias: string): string {
  const base = readAlias.replace(/-read$/, '');
  return `${base}-000001`;
}

/**
 * Build the atomic `_aliases` actions that point BOTH the read and
 * write aliases at a single physical index, removing any stale
 * membership first. Pure — the unit test asserts read + write always
 * land on the same index.
 */
export function buildAliasActions(
  physicalIndex: string,
  readAlias: string,
  writeAlias: string,
  previousReadTargets: string[] = [],
  previousWriteTargets: string[] = [],
): Array<Record<string, unknown>> {
  const actions: Array<Record<string, unknown>> = [];
  for (const index of previousReadTargets) {
    if (index !== physicalIndex) actions.push({ remove: { index, alias: readAlias } });
  }
  for (const index of previousWriteTargets) {
    if (index !== physicalIndex) actions.push({ remove: { index, alias: writeAlias } });
  }
  actions.push({ add: { index: physicalIndex, alias: readAlias } });
  actions.push({ add: { index: physicalIndex, alias: writeAlias, is_write_index: true } });
  return actions;
}

function headers(authHeader?: string): Record<string, string> {
  const base: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authHeader) base.Authorization = authHeader;
  return base;
}

/** Indices for which `alias` is genuinely an alias (not a same-named index). */
async function getAliasTargets(
  node: string,
  alias: string,
  authHeader?: string,
): Promise<string[]> {
  const response = await fetch(`${node}/_alias/${alias}`, { headers: headers(authHeader) });
  if (response.status === 404) return [];
  if (!response.ok) {
    throw new Error(`failed reading alias ${alias}: ${response.status} ${await response.text()}`);
  }
  const payload = (await response.json()) as Record<string, { aliases?: Record<string, unknown> }>;
  return Object.entries(payload)
    .filter(([, value]) => value?.aliases && alias in value.aliases)
    .map(([index]) => index);
}

async function indexExists(node: string, index: string, authHeader?: string): Promise<boolean> {
  const response = await fetch(`${node}/${index}`, {
    method: 'HEAD',
    headers: headers(authHeader),
  });
  return response.ok;
}

/**
 * Replica count a versioned production cutover creates its index with
 * (`scripts/opensearch-alias-cutover.ts`). Lives here rather than in that
 * script because the script executes `main()` on import, so nothing else —
 * including the drift guard — can import from it.
 */
export const CUTOVER_REPLICAS = 1;

/** Replica count the startup bootstrap uses (single-node default). */
export const BOOTSTRAP_REPLICAS = 0;

export interface CreateDocumentsIndexOptions {
  /** Replica count for the new index (bootstrap uses 0, a versioned cutover 1). */
  numberOfReplicas?: number;
  authHeader?: string;
  /**
   * Swallow `resource_already_exists_exception` instead of throwing. True for
   * the startup bootstrap (multiple API replicas race); false for a versioned
   * cutover, where a colliding index name is a real error.
   */
  tolerateExisting?: boolean;
}

/**
 * THE single way to create a documents index. Every producer must call this
 * rather than PUT a mapping of its own — a hand-maintained copy in
 * `scripts/validate-tar89-metadata-local.sh` caused #675, and a mapping-less
 * `PUT` in the GCP runtime tfvars caused #713. Both presented as query bugs,
 * because OpenSearch answers a missing field with empty buckets, not an error.
 *
 * Guarded by the producer registry in `mapping-drift.integration.spec.ts`,
 * which asserts every caller's arguments yield zero drift from canonical.
 */
export async function createDocumentsIndex(
  node: string,
  index: string,
  options: CreateDocumentsIndexOptions = {},
): Promise<void> {
  const { numberOfReplicas = 0, authHeader, tolerateExisting = false } = options;
  const response = await fetch(`${node}/${index}`, {
    method: 'PUT',
    headers: headers(authHeader),
    body: JSON.stringify(documentsIndexDefinition(numberOfReplicas)),
  });
  if (response.ok) return;
  const text = await response.text();
  if (tolerateExisting && text.includes('resource_already_exists_exception')) return;
  throw new Error(`failed creating index ${index}: ${response.status} ${text}`);
}

async function updateAliases(
  node: string,
  actions: Array<Record<string, unknown>>,
  authHeader?: string,
): Promise<void> {
  const response = await fetch(`${node}/_aliases`, {
    method: 'POST',
    headers: headers(authHeader),
    body: JSON.stringify({ actions }),
  });
  if (!response.ok) {
    const text = await response.text();
    if (text.includes('invalid_alias_name_exception')) {
      // A stray physical index shares a name with one of the aliases
      // (e.g. a legacy `documents-write` index). Delete it and re-run.
      throw new Error(`alias collided with a same-named index; delete it and retry: ${text}`);
    }
    throw new Error(`alias update failed: ${response.status} ${text}`);
  }
}

/**
 * Ensure the documents index exists with the canonical mapping and that
 * both aliases resolve to it. Idempotent and non-destructive:
 *  - if the read alias already resolves, nothing is touched (a
 *    versioned cutover manages the aliases in that case);
 *  - otherwise a physical index is created (if absent) and both aliases
 *    are pointed at it atomically.
 */
export async function bootstrapDocumentsIndex(options: BootstrapOptions): Promise<BootstrapResult> {
  const { node, readAlias, writeAlias, authHeader, numberOfReplicas = 0 } = options;
  const logger = options.logger ?? noopLogger;

  const currentReadTargets = await getAliasTargets(node, readAlias, authHeader);
  if (currentReadTargets.length > 0) {
    logger.info(
      `documents index already bootstrapped: ${readAlias} -> [${currentReadTargets.join(', ')}]`,
    );
    return { status: 'exists', physicalIndex: currentReadTargets[0] };
  }

  const physicalIndex = deriveDocumentsPhysicalIndex(readAlias);
  if (!(await indexExists(node, physicalIndex, authHeader))) {
    await createDocumentsIndex(node, physicalIndex, {
      numberOfReplicas,
      authHeader,
      tolerateExisting: true,
    });
    logger.info(`created documents index ${physicalIndex} with canonical mapping`);
  }

  const previousWriteTargets = await getAliasTargets(node, writeAlias, authHeader);
  const actions = buildAliasActions(physicalIndex, readAlias, writeAlias, [], previousWriteTargets);
  await updateAliases(node, actions, authHeader);
  logger.info(`aliases ${readAlias} + ${writeAlias} -> ${physicalIndex}`);

  return { status: 'created', physicalIndex };
}
