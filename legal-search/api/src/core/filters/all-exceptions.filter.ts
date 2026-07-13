import {
  type ArgumentsHost,
  Catch,
  type ExceptionFilter,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import type { Request, Response } from 'express';
import { SearchBackendUnavailableError } from '../../modules/search/search.errors';

/**
 * Global exception filter.
 *
 * Maps all exceptions to a consistent error shape:
 *   { statusCode, message, error, requestId }
 *
 * Domain exceptions (e.g. SearchBackendUnavailableError) are mapped here.
 * Service code should never throw HTTP exceptions directly.
 */
@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  private readonly logger = new Logger(AllExceptionsFilter.name);

  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const request = ctx.getRequest<Request>();

    const requestId = request.headers['x-request-id'] as string | undefined;

    let statusCode = HttpStatus.INTERNAL_SERVER_ERROR;
    let message = 'Internal server error';

    if (exception instanceof HttpException) {
      statusCode = exception.getStatus();
      const res = exception.getResponse();
      message = typeof res === 'string' ? res : ((res as { message?: string }).message ?? message);
    } else if (exception instanceof SearchBackendUnavailableError) {
      // The search backend could not execute the query (missing index/alias,
      // connection refused, timeout). Surfacing it as a 503 is what keeps a
      // dead search index from looking like "no results" (#551).
      statusCode = HttpStatus.SERVICE_UNAVAILABLE;
      message = exception.message;
      this.logger.error(exception.message, exception.stack);
    } else if (exception instanceof Error) {
      // Map known domain exceptions here as the system grows, e.g.:
      // if (exception instanceof DocumentNotFoundError) statusCode = 404;
      this.logger.error(exception.message, exception.stack);
    }

    response.status(statusCode).json({
      statusCode,
      message,
      error: HttpStatus[statusCode],
      requestId,
    });
  }
}
