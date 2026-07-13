import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_FILTER, APP_GUARD } from '@nestjs/core';
import { ApiKeyGuard } from './core/auth/api-key.guard';
import documentIntelligenceConfig from './core/config/document-intelligence.config';
import opensearchConfig from './core/config/opensearch.config';
import { AllExceptionsFilter } from './core/filters/all-exceptions.filter';
import { OpenSearchModule } from './core/opensearch/client';
import { DocumentsModule } from './modules/documents/documents.module';
import { HealthModule } from './modules/health/health.module';
import { ProjectionsModule } from './modules/projections/projections.module';
import { SearchModule } from './modules/search/search.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      load: [opensearchConfig, documentIntelligenceConfig],
    }),
    OpenSearchModule,
    HealthModule,
    SearchModule,
    DocumentsModule,
    ProjectionsModule,
  ],
  providers: [
    {
      provide: APP_GUARD,
      useClass: ApiKeyGuard,
    },
    {
      // ADR-0008 specifies a global exception filter; it existed but was never
      // registered, so domain errors fell through to Nest's default handler.
      provide: APP_FILTER,
      useClass: AllExceptionsFilter,
    },
  ],
})
export class AppModule {}
