import { defineConfig } from 'orval';

/**
 * Generated fetch client for the document-intelligence Document Service.
 * Spec: contracts/api/document-intelligence.openapi.yaml (ADR-0010).
 */
export default defineConfig({
  documentIntelligence: {
    input: {
      target: '../../contracts/api/document-intelligence.openapi.yaml',
    },
    output: {
      target: './src/lib/document-intelligence/generated/api.ts',
      client: 'fetch',
      mode: 'split',
      schemas: './src/lib/document-intelligence/generated/model',
      override: {
        mutator: {
          path: './src/lib/document-intelligence/document-intelligence-mutator.ts',
          name: 'documentIntelligenceFetch',
        },
      },
    },
  },
});
