import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import {
  FetchDocumentIntelligenceClient,
  NoOpDocumentContentClient,
} from './document-intelligence.fetch-client';
import { DocumentsController } from './documents.controller';
import { DOCUMENTS_REPOSITORY } from './documents.repository';
import { DocumentsService } from './documents.service';
import { DocumentsOpenSearchAdapter } from './opensearch.adapter';
import { DOCUMENT_CONTENT_PORT } from './ports/document-content.port';

@Module({
  controllers: [DocumentsController],
  providers: [
    DocumentsService,
    { provide: DOCUMENTS_REPOSITORY, useClass: DocumentsOpenSearchAdapter },
    {
      provide: DOCUMENT_CONTENT_PORT,
      useFactory: (config: ConfigService) => {
        const base = config.get<string>('documentIntelligence.baseUrl') ?? '';
        if (!base) return new NoOpDocumentContentClient();
        return new FetchDocumentIntelligenceClient(config);
      },
      inject: [ConfigService],
    },
  ],
})
export class DocumentsModule {}
