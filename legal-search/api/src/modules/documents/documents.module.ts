import { Module } from '@nestjs/common';
import {
  DOCUMENT_INTELLIGENCE_CLIENT,
  HttpDocumentIntelligenceClient,
} from '../../lib/document-intelligence/document-intelligence.client';
import { CitationsModule } from '../citations/citations.module';
import { DocumentsController } from './documents.controller';
import { DOCUMENTS_REPOSITORY } from './documents.repository';
import { DocumentsService } from './documents.service';
import { DocumentsOpenSearchAdapter } from './opensearch.adapter';

@Module({
  imports: [CitationsModule],
  controllers: [DocumentsController],
  providers: [
    DocumentsService,
    { provide: DOCUMENTS_REPOSITORY, useClass: DocumentsOpenSearchAdapter },
    { provide: DOCUMENT_INTELLIGENCE_CLIENT, useClass: HttpDocumentIntelligenceClient },
  ],
})
export class DocumentsModule {}
