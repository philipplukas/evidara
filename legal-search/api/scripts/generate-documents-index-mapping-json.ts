#!/usr/bin/env npx tsx

/// <reference types="node" />

/**
 * Write `scripts/opensearch/documents-index.mapping.json` from the canonical
 * TypeScript mapping (#675). See `src/core/opensearch/documents-index.mapping-json.ts`
 * for why the artifact exists; `documents-index.mapping-json.spec.ts` fails the
 * build when the committed file and the TypeScript definition disagree.
 *
 *   cd legal-search/api && npm run mapping:generate
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { renderDocumentsIndexMappingJson } from '../src/core/opensearch/documents-index.mapping-json';

const target = resolve(__dirname, '../../../scripts/opensearch/documents-index.mapping.json');
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, renderDocumentsIndexMappingJson(), 'utf8');
console.log(`wrote ${target}`);
