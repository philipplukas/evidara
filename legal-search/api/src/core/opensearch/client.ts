/**
 * OpenSearch client module.
 *
 * Provides a shared Client singleton from config.
 * Import this module in AppModule to make the client available globally.
 */
import { Global, Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Client } from '@opensearch-project/opensearch';

export const OPENSEARCH_CLIENT = Symbol('OPENSEARCH_CLIENT');

export function createOpenSearchClient(nodeUrl: string): Client {
  return new Client({
    node: nodeUrl,
    ssl: nodeUrl.startsWith('https') ? { rejectUnauthorized: false } : undefined,
  });
}

@Global()
@Module({
  providers: [
    {
      provide: OPENSEARCH_CLIENT,
      useFactory: (config: ConfigService) => {
        const node = config.get<string>('opensearch.node') ?? 'http://localhost:9200';
        return createOpenSearchClient(node);
      },
      inject: [ConfigService],
    },
  ],
  exports: [OPENSEARCH_CLIENT],
})
export class OpenSearchModule {}
