import { registerAs } from '@nestjs/config';

/**
 * OpenSearch configuration.
 *
 * Naming convention: field names are domain-level on the outside
 * (`documentsReadAlias`, `sectionsIndex`, ...), while the backing
 * `OPENSEARCH_*` environment variables remain the stable deploy-time
 * contract. Storage-level concepts (alias vs. index) are reflected in
 * the field suffix only where the value is in fact an alias.
 *
 * Consumers must read via these domain-level keys; the OpenSearch
 * client adapters are the only place that translates them to a
 * concrete index/alias at query time.
 */
export default registerAs('opensearch', () => ({
  node: process.env.OPENSEARCH_NODE ?? 'http://localhost:9200',
  documentsReadAlias: process.env.OPENSEARCH_ALIAS_READ ?? 'documents-read',
  documentsWriteAlias: process.env.OPENSEARCH_ALIAS_WRITE ?? 'documents-write',
  sectionsIndex: process.env.OPENSEARCH_INDEX_SECTIONS ?? 'sections',
  citationsIndex: process.env.OPENSEARCH_INDEX_CITATIONS ?? 'citations',
  citationTargetsIndex: process.env.OPENSEARCH_INDEX_CITATION_TARGETS ?? 'citation-targets',
  projectionHistoryIndex: process.env.OPENSEARCH_INDEX_PROJECTION_HISTORY ?? 'projection-history',
  citationTargetsIndex: process.env.OPENSEARCH_INDEX_CITATION_TARGETS ?? 'citation-targets',
}));
