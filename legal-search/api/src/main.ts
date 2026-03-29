import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { AppModule } from './app.module';
import { AllExceptionsFilter } from './core/filters/all-exceptions.filter';
import { LoggingInterceptor } from './core/interceptors/logging.interceptor';
import { ConfigService } from '@nestjs/config';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  const config = app.get(ConfigService);
  const port = config.get<number>('PORT', 3001);

  // Global validation — whitelist strips unknown fields, transform coerces types
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }),
  );

  // Global exception filter — maps domain errors to consistent HTTP shapes
  app.useGlobalFilters(new AllExceptionsFilter());

  // Global logging interceptor — logs request/response with correlation ID
  app.useGlobalInterceptors(new LoggingInterceptor());

  // Swagger UI — available at /api in development
  if (config.get('NODE_ENV') !== 'production') {
    const swaggerConfig = new DocumentBuilder()
      .setTitle('Legal Search API')
      .setDescription(
        'Search and document endpoints. Canonical spec: contracts/api/legal-search.openapi.yaml',
      )
      .setVersion('0.1.0')
      .addBearerAuth()
      .addTag('search', 'Document search')
      .addTag('documents', 'Document detail and sections')
      .addTag('health', 'Health check')
      .build();

    const document = SwaggerModule.createDocument(app, swaggerConfig);
    SwaggerModule.setup('api', app, document);
  }

  await app.listen(port);
  console.log(`legal-search api running on port ${port}`);
}

bootstrap();
