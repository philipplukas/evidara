#!/usr/bin/env npx tsx

/// <reference types="node" />

/**
 * Create a new versioned projection index and atomically cut over
 * the stable read/write aliases used by legal-search.
 *
 * Three modes:
 *
 * 1. Cutover (default) — create a new index, optionally copy data from the
 *    previous index (`--reindex`), then swap both aliases at once.
 *
 * 2. `--stage-write` — create a new index and move only the WRITE alias to it.
 *    The READ alias keeps serving the old index, so a Delta-sourced rebuild can
 *    fill the new index while live traffic is unaffected. This is what makes a
 *    versioned reindex sourceable from canonical truth rather than from the
 *    previous index (ADR-0005): OpenSearch's own `_reindex` cannot help when the
 *    old index is gone or when its contents are degraded.
 *
 * 3. `--promote-read --index <name>` — point the READ alias at a staged index,
 *    completing the cutover.
 *
 * Usage:
 *   npx tsx scripts/opensearch-alias-cutover.ts
 *   npx tsx scripts/opensearch-alias-cutover.ts --reindex
 *
 *   # Delta-sourced versioned reindex (see docs/runbooks/projection-reindex-backfill.md):
 *   npx tsx scripts/opensearch-alias-cutover.ts --stage-write
 *   document_intelligence_delta_projection_backfill --resume   # fills the staged index
 *   npx tsx scripts/opensearch-alias-cutover.ts --promote-read --index <staged-index>
 */

import {
  type AliasAction,
  cutoverAliasActions,
  moveAliasActions,
} from '../src/core/opensearch/alias-actions';
import { CUTOVER_REPLICAS, createDocumentsIndex } from '../src/core/opensearch/documents-bootstrap';

const args = process.argv.slice(2);
const shouldReindex = args.includes('--reindex');
const dryRun = args.includes('--dry-run');
const stageWrite = args.includes('--stage-write');
const promoteRead = args.includes('--promote-read');

function flagValue(flag: string): string | undefined {
  const index = args.indexOf(flag);
  if (index === -1) return undefined;
  const value = args[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`missing value for ${flag}`);
  }
  return value;
}

const sourceIndexArg = flagValue('--source-index');
const promoteIndexArg = flagValue('--index');

if (stageWrite && promoteRead) {
  throw new Error('--stage-write and --promote-read are separate phases; run them one at a time');
}
if (promoteRead && !promoteIndexArg) {
  throw new Error('--promote-read requires --index <staged-index-name>');
}

const node = process.env.OPENSEARCH_NODE ?? 'http://localhost:9200';
const readAlias = process.env.OPENSEARCH_ALIAS_READ ?? 'evidara-documents-read-dev';
const writeAlias = process.env.OPENSEARCH_ALIAS_WRITE ?? 'evidara-documents-write-dev';
const versionSuffix = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14);
const nextIndex = `${readAlias}-${versionSuffix}`;

const authHeader = (() => {
  const username = process.env.OPENSEARCH_USERNAME;
  const password = process.env.OPENSEARCH_PASSWORD;
  if (!username || !password) return undefined;
  return `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`;
})();

async function osFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (authHeader) headers.Authorization = authHeader;
  return fetch(`${node}${path}`, { ...init, headers });
}

async function ensureIndex(indexName: string): Promise<void> {
  // Canonical mapping via the shared creator — see the producer registry in
  // `mapping-drift.integration.spec.ts`, which guards this exact call shape.
  // A colliding index name during a cutover is a real error, so we do not
  // tolerate `resource_already_exists_exception` here.
  await createDocumentsIndex(node, indexName, {
    numberOfReplicas: CUTOVER_REPLICAS,
    authHeader,
  });
}

async function getAliasIndices(aliasName: string): Promise<string[]> {
  const response = await osFetch(`/_alias/${aliasName}`, { method: 'GET' });
  if (response.status === 404) return [];
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`failed reading alias ${aliasName}: ${response.status} ${body}`);
  }
  const payload = (await response.json()) as Record<string, unknown>;
  return Object.keys(payload);
}

async function reindex(sourceIndex: string, destinationIndex: string): Promise<void> {
  const response = await osFetch('/_reindex?wait_for_completion=true', {
    method: 'POST',
    body: JSON.stringify({
      source: { index: sourceIndex },
      dest: { index: destinationIndex, op_type: 'create' },
      conflicts: 'proceed',
    }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`reindex failed: ${response.status} ${body}`);
  }
}

async function applyAliasActions(actions: AliasAction[]): Promise<void> {
  const response = await osFetch('/_aliases', {
    method: 'POST',
    body: JSON.stringify({ actions }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`alias update failed: ${response.status} ${body}`);
  }
}

async function cutoverAliases(
  previousReadTargets: string[],
  previousWriteTargets: string[],
  destinationIndex: string,
): Promise<void> {
  await applyAliasActions(
    cutoverAliasActions(
      readAlias,
      writeAlias,
      previousReadTargets,
      previousWriteTargets,
      destinationIndex,
    ),
  );
}

async function indexExists(indexName: string): Promise<boolean> {
  const response = await osFetch(`/${indexName}`, { method: 'HEAD' });
  return response.ok;
}

async function countDocuments(indexName: string): Promise<number | undefined> {
  const response = await osFetch(`/${indexName}/_count`, { method: 'GET' });
  if (!response.ok) return undefined;
  const payload = (await response.json()) as { count?: number };
  return payload.count;
}

/**
 * Phase 1 of a Delta-sourced versioned reindex: create the new index and move only
 * the WRITE alias onto it. Reads keep serving the previous index, so the backfill
 * (and any concurrent live projection) fills the new index with zero user impact.
 */
async function stageWriteMain(): Promise<void> {
  console.log(`[1/3] Creating new projection index: ${nextIndex}`);
  if (!dryRun) {
    await ensureIndex(nextIndex);
  }

  console.log('[2/3] Reading current alias targets...');
  const currentReadTargets = await getAliasIndices(readAlias);
  const currentWriteTargets = await getAliasIndices(writeAlias);
  console.log(`  read alias → [${currentReadTargets.join(', ')}]`);
  console.log(`  write alias → [${currentWriteTargets.join(', ')}]`);

  console.log(`[3/3] Staging write alias: ${writeAlias} → ${nextIndex} (read alias unchanged)`);
  if (!dryRun) {
    await applyAliasActions(moveAliasActions(writeAlias, currentWriteTargets, nextIndex, true));
    console.log('Write alias staged ✓');
  } else {
    console.log(`  [DRY RUN] Would point ${writeAlias} at ${nextIndex}`);
  }

  console.log('');
  console.log('Next: rebuild the staged index from canonical Delta, then promote reads:');
  console.log('  document_intelligence_delta_projection_backfill --resume');
  console.log(
    `  npx tsx scripts/opensearch-alias-cutover.ts --promote-read --index ${nextIndex}`,
  );
}

/** Phase 2: point the READ alias at a staged index that the backfill has filled. */
async function promoteReadMain(): Promise<void> {
  const target = promoteIndexArg as string;

  console.log(`[1/3] Verifying staged index: ${target}`);
  if (!(await indexExists(target))) {
    throw new Error(`staged index ${target} does not exist`);
  }
  const stagedCount = await countDocuments(target);
  console.log(`  ${target} document count → ${stagedCount ?? 'unknown'}`);
  if (stagedCount === 0) {
    throw new Error(
      `refusing to promote ${target}: it contains 0 documents (run the Delta backfill first)`,
    );
  }

  console.log('[2/3] Reading current alias targets...');
  const currentReadTargets = await getAliasIndices(readAlias);
  console.log(`  read alias → [${currentReadTargets.join(', ')}]`);
  for (const previous of currentReadTargets) {
    if (previous === target) continue;
    console.log(`  ${previous} document count → ${(await countDocuments(previous)) ?? 'unknown'}`);
  }

  console.log(`[3/3] Promoting read alias: ${readAlias} → ${target}`);
  if (!dryRun) {
    await applyAliasActions(moveAliasActions(readAlias, currentReadTargets, target));
    console.log('Read alias promoted ✓');
  } else {
    console.log(`  [DRY RUN] Would point ${readAlias} at ${target}`);
  }
}

async function cutoverMain(): Promise<void> {
  console.log(`[1/4] Creating new projection index: ${nextIndex}`);
  if (!dryRun) {
    await ensureIndex(nextIndex);
  }

  console.log(`[2/4] Reading current alias targets...`);
  const currentReadTargets = await getAliasIndices(readAlias);
  const currentWriteTargets = await getAliasIndices(writeAlias);
  console.log(`  read alias → [${currentReadTargets.join(', ')}]`);
  console.log(`  write alias → [${currentWriteTargets.join(', ')}]`);

  if (shouldReindex) {
    const sourceIndex = sourceIndexArg ?? (() => {
      if (currentReadTargets.length === 1) return currentReadTargets[0];
      if (currentReadTargets.length > 1) {
        throw new Error(
          `multiple read alias targets found (${currentReadTargets.join(', ')}); pass --source-index to choose source index`,
        );
      }
      return undefined;
    })();

    if (sourceIndex) {
      console.log(`[3/4] Reindexing data: ${sourceIndex} → ${nextIndex}`);
      if (!dryRun) {
        const start = Date.now();
        await reindex(sourceIndex, nextIndex);
        console.log(`  Reindex completed in ${((Date.now() - start) / 1000).toFixed(1)}s`);
      } else {
        console.log(`  [DRY RUN] Would reindex from ${sourceIndex}`);
      }
    } else {
      console.log(`[3/4] Skipping reindex — no current read alias targets`);
    }
  } else {
    console.log(`[3/4] Skipping reindex (not requested)`);
  }

  console.log(`[4/4] Cutting over aliases: read=${readAlias}, write=${writeAlias} → ${nextIndex}`);
  if (!dryRun) {
    await cutoverAliases(currentReadTargets, currentWriteTargets, nextIndex);
    console.log('Alias cutover complete ✓');
  } else {
    console.log(`  [DRY RUN] Would remove ${currentReadTargets.length} read + ${currentWriteTargets.length} write targets, point to ${nextIndex}`);
  }
}

async function main(): Promise<void> {
  if (dryRun) {
    console.log('[DRY RUN] No changes will be made.');
  }

  if (promoteRead) return promoteReadMain();
  if (stageWrite) return stageWriteMain();
  return cutoverMain();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
