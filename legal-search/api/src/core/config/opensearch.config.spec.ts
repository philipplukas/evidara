import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import opensearchConfig from './opensearch.config';

const ENV_KEYS = [
  'OPENSEARCH_NODE',
  'OPENSEARCH_ALIAS_READ',
  'OPENSEARCH_ALIAS_WRITE',
  'OPENSEARCH_INDEX_SECTIONS',
  'OPENSEARCH_INDEX_CITATIONS',
  'OPENSEARCH_INDEX_CITATION_TARGETS',
  'OPENSEARCH_INDEX_PROJECTION_HISTORY',
] as const;

describe('opensearch.config', () => {
  const originalEnv: Partial<Record<(typeof ENV_KEYS)[number], string | undefined>> = {};

  beforeEach(() => {
    for (const key of ENV_KEYS) {
      originalEnv[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      if (originalEnv[key] === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = originalEnv[key];
      }
    }
  });

  it('exposes domain-level field names with safe defaults when env is unset', () => {
    const config = opensearchConfig();

    expect(config).toEqual({
      node: 'http://localhost:9200',
      documentsReadAlias: 'documents-read',
      documentsWriteAlias: 'documents-write',
      sectionsIndex: 'sections',
      citationsIndex: 'citations',
      citationTargetsIndex: 'citation-targets',
      projectionHistoryIndex: 'projection-history',
    });
  });

  it('reads every field from its OPENSEARCH_* environment variable', () => {
    process.env.OPENSEARCH_NODE = 'http://opensearch.example:9200';
    process.env.OPENSEARCH_ALIAS_READ = 'docs-read-prod';
    process.env.OPENSEARCH_ALIAS_WRITE = 'docs-write-prod';
    process.env.OPENSEARCH_INDEX_SECTIONS = 'sections-prod';
    process.env.OPENSEARCH_INDEX_CITATIONS = 'citations-prod';
    process.env.OPENSEARCH_INDEX_CITATION_TARGETS = 'citation-targets-prod';
    process.env.OPENSEARCH_INDEX_PROJECTION_HISTORY = 'projection-history-prod';

    const config = opensearchConfig();

    expect(config).toEqual({
      node: 'http://opensearch.example:9200',
      documentsReadAlias: 'docs-read-prod',
      documentsWriteAlias: 'docs-write-prod',
      sectionsIndex: 'sections-prod',
      citationsIndex: 'citations-prod',
      citationTargetsIndex: 'citation-targets-prod',
      projectionHistoryIndex: 'projection-history-prod',
    });
  });

  it('exposes one canonical field per env var (no duplicate synonyms)', () => {
    process.env.OPENSEARCH_ALIAS_READ = 'shared-read';
    process.env.OPENSEARCH_ALIAS_WRITE = 'shared-write';

    const config = opensearchConfig() as Record<string, unknown>;

    // Deduplicated: old aliasRead/indexDocumentsRead synonyms are gone.
    expect(config).not.toHaveProperty('aliasRead');
    expect(config).not.toHaveProperty('aliasWrite');
    expect(config).not.toHaveProperty('indexDocumentsRead');
    expect(config).not.toHaveProperty('indexDocumentsWrite');

    // A single canonical field maps to each env var.
    expect(config.documentsReadAlias).toBe('shared-read');
    expect(config.documentsWriteAlias).toBe('shared-write');
  });
});
