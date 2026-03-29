import { registerAs } from '@nestjs/config';

export default registerAs('opensearch', () => ({
  url: process.env['OPENSEARCH_URL'] ?? 'http://localhost:9200',
  indexDocuments: process.env['OPENSEARCH_INDEX_DOCUMENTS'] ?? 'evidara-documents-v1',
  indexSections: process.env['OPENSEARCH_INDEX_SECTIONS'] ?? 'evidara-sections-v1',
}));
