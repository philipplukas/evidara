import { Module } from '@nestjs/common';
import { CoverageController } from './coverage.controller';
import { COVERAGE_REPOSITORY } from './coverage.repository';
import { CoverageService } from './coverage.service';
import { CoverageOpenSearchAdapter } from './opensearch.adapter';

@Module({
  controllers: [CoverageController],
  providers: [
    CoverageService,
    { provide: COVERAGE_REPOSITORY, useClass: CoverageOpenSearchAdapter },
  ],
})
export class CoverageModule {}
