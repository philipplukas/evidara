import { Module } from '@nestjs/common';
import {
  DOCUMENT_INTELLIGENCE_CLIENT,
  HttpDocumentIntelligenceClient,
} from '../../lib/document-intelligence/document-intelligence.client';
import { ProjectionOpenSearchAdapter } from './opensearch.adapter';
import { ProjectionsController } from './projections.controller';
import { PROJECTION_REPOSITORY } from './projections.repository';
import { ProjectionsService } from './projections.service';

@Module({
  controllers: [ProjectionsController],
  providers: [
    ProjectionsService,
    ProjectionOpenSearchAdapter,
    {
      provide: PROJECTION_REPOSITORY,
      useExisting: ProjectionOpenSearchAdapter,
    },
    { provide: DOCUMENT_INTELLIGENCE_CLIENT, useClass: HttpDocumentIntelligenceClient },
  ],
})
export class ProjectionsModule {}
