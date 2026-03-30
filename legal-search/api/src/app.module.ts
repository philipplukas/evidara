import { type MiddlewareConsumer, Module, type NestModule } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import appConfig from './core/config/app.config';
import opensearchConfig from './core/config/opensearch.config';
import { CorrelationIdMiddleware } from './core/middleware/correlation-id.middleware';
import { DocumentsModule } from './modules/documents/documents.module';
import { HealthModule } from './modules/health/health.module';
import { SearchModule } from './modules/search/search.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      load: [appConfig, opensearchConfig],
      // Validates required env vars at startup — fail fast rather than at runtime
      validationOptions: { allowUnknown: true },
    }),
    HealthModule,
    SearchModule,
    DocumentsModule,
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(CorrelationIdMiddleware).forRoutes('*');
  }
}
