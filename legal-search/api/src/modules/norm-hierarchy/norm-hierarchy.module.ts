import { Module } from '@nestjs/common';
import { NormHierarchyController } from './norm-hierarchy.controller';
import { NORM_HIERARCHY_REPOSITORY } from './norm-hierarchy.repository';
import { NormHierarchyService } from './norm-hierarchy.service';
import { NormHierarchyOpenSearchAdapter } from './opensearch.adapter';

@Module({
  controllers: [NormHierarchyController],
  providers: [
    NormHierarchyService,
    { provide: NORM_HIERARCHY_REPOSITORY, useClass: NormHierarchyOpenSearchAdapter },
  ],
})
export class NormHierarchyModule {}
