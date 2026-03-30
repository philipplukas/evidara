import { Module } from '@nestjs/common';
import { DocumentsController } from './documents.controller';
import { DOCUMENTS_REPOSITORY } from './documents.repository';
import { DocumentsService } from './documents.service';
import { OpenSearchDocumentsAdapter } from './opensearch.adapter';

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
