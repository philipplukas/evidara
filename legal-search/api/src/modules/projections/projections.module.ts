import { Module } from '@nestjs/common';
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
  ],
})
export class ProjectionsModule {}
