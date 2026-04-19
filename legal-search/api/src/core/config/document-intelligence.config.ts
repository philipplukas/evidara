import { registerAs } from '@nestjs/config';

export const readDocumentIntelligenceRuntimeEnv = (): {
  baseUrl: string;
  apiKey: string | undefined;
} => ({
  baseUrl: (process.env.DOCUMENT_INTELLIGENCE_BASE_URL ?? '').trim().replace(/\/$/, ''),
  apiKey: process.env.DOCUMENT_INTELLIGENCE_API_KEY?.trim() || undefined,
});

export default registerAs('documentIntelligence', () => ({
  baseUrl: (process.env.DOCUMENT_INTELLIGENCE_BASE_URL ?? '').trim().replace(/\/$/, ''),
}));
