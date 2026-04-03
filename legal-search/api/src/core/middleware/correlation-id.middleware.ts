import { Injectable, type NestMiddleware } from '@nestjs/common';
import type { NextFunction, Request, Response } from 'express';
import { v4 as uuidv4 } from 'uuid';

/**
 * Attaches a correlation ID to every request.
 * Reads from the incoming X-Request-ID header if present, otherwise generates a new UUID.
 * Passes the ID downstream in the response header for client tracing.
 */
@Injectable()
export class CorrelationIdMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction) {
    const raw = req.headers['x-correlation-id'] ?? req.headers['x-request-id'];
    const requestId = typeof raw === 'string' ? raw : Array.isArray(raw) ? raw[0] : uuidv4();
    req.headers['x-request-id'] = requestId;
    req.headers['x-correlation-id'] = requestId;
    res.setHeader('X-Correlation-Id', requestId);
    res.setHeader('X-Request-ID', requestId);
    next();
  }
}
