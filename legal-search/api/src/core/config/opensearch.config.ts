import { registerAs } from '@nestjs/config';

export default registerAs('opensearch', () => ({
  node: process.env.OPENSEARCH_NODE ?? 'http://localhost:9200',
  indexDocumentsRead: process.env.OPENSEARCH_ALIAS_READ ?? 'documents-read',
  indexDocumentsWrite: process.env.OPENSEARCH_ALIAS_WRITE ?? 'documents-write',
  indexSections: process.env.OPENSEARCH_INDEX_SECTIONS ?? 'sections',
  indexCitations: process.env.OPENSEARCH_INDEX_CITATIONS ?? 'citations',
  indexProjectionHistory: process.env.OPENSEARCH_INDEX_PROJECTION_HISTORY ?? 'projection-history',
  aliasRead: process.env.OPENSEARCH_ALIAS_READ ?? 'documents-read',
  aliasWrite: process.env.OPENSEARCH_ALIAS_WRITE ?? 'documents-write',
}));
