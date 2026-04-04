import type { CallHandler, ExecutionContext } from '@nestjs/common';
import { of } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';
import { PubSubUnwrapInterceptor } from './pubsub-unwrap.interceptor';

function createMockContext(body: unknown): ExecutionContext {
  const req = { body };
  return {
    switchToHttp: () => ({
      getRequest: () => req,
      getResponse: () => ({}),
      getNext: () => vi.fn(),
    }),
    getClass: () => Object,
    getHandler: () => vi.fn(),
    getArgs: () => [req],
    getArgByIndex: () => req,
    switchToRpc: () => ({}) as ReturnType<ExecutionContext['switchToRpc']>,
    switchToWs: () => ({}) as ReturnType<ExecutionContext['switchToWs']>,
    getType: () => 'http' as const,
  } as unknown as ExecutionContext;
}

const nextHandler: CallHandler = {
  handle: () => of('ok'),
};

describe('PubSubUnwrapInterceptor', () => {
  const interceptor = new PubSubUnwrapInterceptor();

  it('unwraps a Pub/Sub push envelope', () => {
    const innerPayload = { event_type: 'document.processed', event_id: 'evt_1' };
    const encoded = Buffer.from(JSON.stringify(innerPayload)).toString('base64');
    const pubsubEnvelope = {
      message: {
        data: encoded,
        messageId: '123456',
        publishTime: '2026-04-04T10:00:00Z',
      },
      subscription: 'projects/my-project/subscriptions/legal-search-document-processed',
    };

    const ctx = createMockContext(pubsubEnvelope);
    interceptor.intercept(ctx, nextHandler);

    const req = ctx.switchToHttp().getRequest();
    expect(req.body).toEqual(innerPayload);
  });

  it('passes through a raw event body unchanged', () => {
    const rawEvent = { event_type: 'document.processed', event_id: 'evt_1' };
    const ctx = createMockContext(rawEvent);
    interceptor.intercept(ctx, nextHandler);

    const req = ctx.switchToHttp().getRequest();
    expect(req.body).toEqual(rawEvent);
  });

  it('passes through if message.data is not a string', () => {
    const badEnvelope = { message: { data: 12345 } };
    const ctx = createMockContext(badEnvelope);
    interceptor.intercept(ctx, nextHandler);

    const req = ctx.switchToHttp().getRequest();
    expect(req.body).toEqual(badEnvelope);
  });

  it('keeps original body if payload cannot be parsed', () => {
    const badEnvelope = { message: { data: '!!!not-base64' } };
    const ctx = createMockContext(badEnvelope);
    interceptor.intercept(ctx, nextHandler);

    const req = ctx.switchToHttp().getRequest();
    expect(req.body).toEqual(badEnvelope);
  });
});
