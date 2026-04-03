#!/usr/bin/env npx tsx

/// <reference types="node" />

/**
 * Create a new versioned projection index and atomically cut over
 * the stable read/write aliases used by legal-search.
 *
 * Usage:
 *   npx tsx scripts/opensearch-alias-cutover.ts
 *   OPENSEARCH_NODE=http://localhost:9200 OPENSEARCH_ALIAS_READ=evidara-documents-read-dev npx tsx scripts/opensearch-alias-cutover.ts --reindex
 */

const args = process.argv.slice(2);
const shouldReindex = args.includes('--reindex');
const sourceIndexArg = (() => {
  const sourceIndexArgIndex = args.indexOf('--source-index');
  if (sourceIndexArgIndex === -1) return undefined;
  const value = args[sourceIndexArgIndex + 1];
  if (!value) {
    throw new Error('missing value for --source-index');
  }
  return value;
})();

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
  const mapping = {
    settings: {
      number_of_shards: 1,
      number_of_replicas: 1,
      analysis: {
        analyzer: {
          legal_text: {
            type: 'custom',
            tokenizer: 'standard',
            filter: ['lowercase', 'german_normalization'],
          },
        },
      },
    },
    mappings: {
      properties: {
        document_id: { type: 'keyword' },
        title: { type: 'text', analyzer: 'legal_text', fields: { keyword: { type: 'keyword' } } },
        jurisdiction: { type: 'keyword' },
        document_type: { type: 'keyword' },
        language: { type: 'keyword' },
        effective_date: { type: 'date', format: 'yyyy-MM-dd' },
        structural_path: { type: 'text', fields: { keyword: { type: 'keyword' } } },
        content: { type: 'text', analyzer: 'legal_text' },
        content_preview: { type: 'text' },
        sections_count: { type: 'integer' },
        citations_count: { type: 'integer' },
        related_decisions_count: { type: 'integer' },
        related_commentary_count: { type: 'integer' },
        source_id: { type: 'keyword' },
        processed_at: { type: 'date' },
        document_revision: { type: 'long' },
        lifecycle_status: { type: 'keyword' },
      },
    },
  };

  const response = await osFetch(`/${indexName}`, {
    method: 'PUT',
    body: JSON.stringify(mapping),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`failed creating index ${indexName}: ${response.status} ${body}`);
  }
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

async function cutoverAliases(
  previousReadTargets: string[],
  previousWriteTargets: string[],
  destinationIndex: string,
): Promise<void> {
  const actions: Array<Record<string, unknown>> = [];
  for (const indexName of previousReadTargets) {
    actions.push({ remove: { index: indexName, alias: readAlias } });
  }
  for (const indexName of previousWriteTargets) {
    actions.push({ remove: { index: indexName, alias: writeAlias } });
  }
  actions.push({ add: { index: destinationIndex, alias: readAlias } });
  actions.push({ add: { index: destinationIndex, alias: writeAlias, is_write_index: true } });

  const response = await osFetch('/_aliases', {
    method: 'POST',
    body: JSON.stringify({ actions }),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`alias cutover failed: ${response.status} ${body}`);
  }
}

async function main(): Promise<void> {
  console.log(`creating new projection index: ${nextIndex}`);
  await ensureIndex(nextIndex);

  const currentReadTargets = await getAliasIndices(readAlias);
  const currentWriteTargets = await getAliasIndices(writeAlias);

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
      console.log(`reindexing data from ${sourceIndex} to ${nextIndex}`);
      await reindex(sourceIndex, nextIndex);
    } else {
      console.log(`--reindex requested but read alias ${readAlias} has no current targets; skipping reindex`);
    }
  }

  console.log(`cutting over aliases: read=${readAlias}, write=${writeAlias}`);
  await cutoverAliases(currentReadTargets, currentWriteTargets, nextIndex);
  console.log('alias cutover complete');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
