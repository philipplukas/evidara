import { registerAs } from '@nestjs/config';

/** Optional integration with document-intelligence Document Service (contracts/api/document-intelligence.openapi.yaml). */
export default registerAs('documentIntelligence', () => ({
  baseUrl: (process.env.DOCUMENT_INTELLIGENCE_BASE_URL ?? '').replace(/\/$/, ''),
  bearerToken: process.env.DOCUMENT_INTELLIGENCE_BEARER_TOKEN ?? '',
}));
