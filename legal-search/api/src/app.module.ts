import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
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
})
export class AppModule {}
