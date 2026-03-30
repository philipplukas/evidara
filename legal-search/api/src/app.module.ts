import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import opensearchConfig from './core/config/opensearch.config';
import { DocumentsModule } from './modules/documents/documents.module';
import { HealthModule } from './modules/health/health.module';
import { SearchModule } from './modules/search/search.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      load: [opensearchConfig],
    }),
    HealthModule,
    SearchModule,
    DocumentsModule,
  ],
})
export class AppModule {}
