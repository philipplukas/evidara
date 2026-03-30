import { registerAs } from '@nestjs/config';

export default registerAs('opensearch', () => {
  const url = process.env.OPENSEARCH_URL ?? 'http://localhost:9200';
  const indexDocuments = process.env.OPENSEARCH_INDEX_DOCUMENTS ?? 'evidara-documents-v1';
  const indexSections = process.env.OPENSEARCH_INDEX_SECTIONS ?? 'evidara-sections-v1';

  // Fail fast on obviously invalid config rather than at first request time.
  try {
    new URL(url);
  } catch {
    throw new Error(`Invalid OPENSEARCH_URL: '${url}'. Must be a valid URL.`);
  }
  if (!indexDocuments) {
    throw new Error('OPENSEARCH_INDEX_DOCUMENTS must not be empty.');
  }
  if (!indexSections) {
    throw new Error('OPENSEARCH_INDEX_SECTIONS must not be empty.');
  }

  return { url, indexDocuments, indexSections };
});
