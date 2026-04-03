import { registerAs } from '@nestjs/config';

export default registerAs('documentIntelligence', () => ({
  baseUrl: (process.env.DOCUMENT_INTELLIGENCE_BASE_URL ?? '').trim().replace(/\/$/, ''),
}));
