import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD } from '@nestjs/core';
import { ApiKeyGuard } from './core/auth/api-key.guard';
import documentIntelligenceConfig from './core/config/document-intelligence.config';
import opensearchConfig from './core/config/opensearch.config';
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
  ],
})
export class AppModule {}
