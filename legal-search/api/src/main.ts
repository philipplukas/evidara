import { Logger, ValidationPipe } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { bootstrapDocumentsIndex } from './core/opensearch/documents-bootstrap';

/**
 * Idempotently ensure the documents index + read/write aliases exist so
 * projected documents surface in search on a fresh (e.g. Hetzner)
 * deploy. Failures are logged, never fatal — the API degrades gracefully
 * when OpenSearch is unavailable.
 */
async function bootstrapOpenSearch(config: ConfigService): Promise<void> {
  if (!config.get<boolean>('opensearch.bootstrapOnStartup')) return;
  const logger = new Logger('OpenSearchBootstrap');
  try {
    const result = await bootstrapDocumentsIndex({
      node: config.get<string>('opensearch.node') ?? 'http://localhost:9200',
      readAlias: config.get<string>('opensearch.documentsReadAlias') ?? 'documents-read',
      writeAlias: config.get<string>('opensearch.documentsWriteAlias') ?? 'documents-write',
      logger: { info: (m) => logger.log(m), warn: (m) => logger.warn(m) },
    });
    logger.log(`documents index bootstrap ${result.status}: ${result.physicalIndex}`);
  } catch (err) {
    logger.warn(`documents index bootstrap skipped: ${(err as Error).message}`);
  }
}

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  const config = app.get(ConfigService);
  const port = config.get<number>('PORT', 3102);

  await bootstrapOpenSearch(config);

  // CORS — allow the frontend dev server to call the API
  app.enableCors({
    origin: config.get('CORS_ORIGIN', 'http://localhost:3101'),
    methods: ['GET', 'POST', 'PUT', 'DELETE'],
    credentials: true,
  });

  // Global validation — whitelist strips unknown fields, transform coerces types
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      transformOptions: { enableImplicitConversion: false },
    }),
  );

  await app.listen(port);
  console.log(`Legal Search API listening on port ${port}`);
}

bootstrap();
