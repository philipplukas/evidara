import { Module } from '@nestjs/common';
import { DocumentsController } from './documents.controller';
import { DOCUMENTS_REPOSITORY } from './documents.repository';
import { DocumentsService } from './documents.service';
import { DocumentsOpenSearchAdapter } from './opensearch.adapter';

@Module({
  controllers: [DocumentsController],
  providers: [
    DocumentsService,
    { provide: DOCUMENTS_REPOSITORY, useClass: DocumentsOpenSearchAdapter },
  ],
})
export class DocumentsModule {}
