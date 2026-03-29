import { Module } from '@nestjs/common';
import { DocumentsController } from './documents.controller';
import { DocumentsService } from './documents.service';
import { OpenSearchDocumentsAdapter } from './opensearch.adapter';
import { DOCUMENTS_REPOSITORY } from './documents.repository';

@Module({
  controllers: [DocumentsController],
  providers: [
    DocumentsService,
    {
      provide: DOCUMENTS_REPOSITORY,
      useClass: OpenSearchDocumentsAdapter,
    },
  ],
})
export class DocumentsModule {}
