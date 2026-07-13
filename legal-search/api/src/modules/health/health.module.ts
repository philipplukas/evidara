import { Module } from '@nestjs/common';
import { SearchModule } from '../search/search.module';
import { HealthController } from './health.controller';

@Module({
  // The read-alias readiness check runs through the search repository so the
  // OpenSearch call lives in the adapter, not in the controller (ADR-0008).
  imports: [SearchModule],
  controllers: [HealthController],
})
export class HealthModule {}
