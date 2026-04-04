import {
  type CallHandler,
  type ExecutionContext,
  Injectable,
  Logger,
  type NestInterceptor,
} from '@nestjs/common';
import type { Observable } from 'rxjs';

/**
 * Unwraps Pub/Sub push messages before they reach the controller.
 *
 * Pub/Sub push subscriptions deliver messages in a standard envelope:
 * ```json
 * {
 *   "message": {
 *     "data": "<base64-encoded-json>",
 *     "messageId": "...",
 *     "publishTime": "..."
 *   },
 *   "subscription": "projects/.../subscriptions/..."
 * }
 * ```
 *
 * This interceptor detects the envelope format and replaces `req.body`
 * with the decoded inner payload, so downstream DTOs and pipes see
 * the raw domain event.  If the body is already a raw event (e.g. in
 * tests or direct calls), it passes through unchanged.
 */
@Injectable()
export class PubSubUnwrapInterceptor implements NestInterceptor {
  private readonly logger = new Logger(PubSubUnwrapInterceptor.name);

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const req = context.switchToHttp().getRequest();
    const body = req.body;

    if (body?.message?.data && typeof body.message.data === 'string') {
      try {
        const decoded = Buffer.from(body.message.data, 'base64').toString('utf-8');
        req.body = JSON.parse(decoded);
        this.logger.debug({
          event: 'pubsub_envelope_unwrapped',
          messageId: body.message.messageId,
          subscription: body.subscription,
        });
      } catch (error) {
        this.logger.warn({
          event: 'pubsub_envelope_decode_failed',
          messageId: body.message.messageId,
          error: error instanceof Error ? error.message : String(error),
        });
        // Let the body pass through as-is; validation will catch it.
      }
    }

    return next.handle();
  }
}
