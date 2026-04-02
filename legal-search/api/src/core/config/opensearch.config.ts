import { registerAs } from '@nestjs/config';

export default registerAs('opensearch', () => ({
  node: process.env.OPENSEARCH_NODE ?? 'http://localhost:9200',
  indexDocuments: process.env.OPENSEARCH_INDEX_DOCUMENTS ?? 'documents',
  indexSections: process.env.OPENSEARCH_INDEX_SECTIONS ?? 'sections',
  indexCitations: process.env.OPENSEARCH_INDEX_CITATIONS ?? 'citations',
}));
