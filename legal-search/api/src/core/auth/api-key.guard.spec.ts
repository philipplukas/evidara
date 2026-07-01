import type { ExecutionContext } from '@nestjs/common';
import { UnauthorizedException } from '@nestjs/common';
import type { ConfigService } from '@nestjs/config';
import type { Reflector } from '@nestjs/core';
import { describe, expect, it } from 'vitest';
import { ApiKeyGuard } from './api-key.guard';

function makeGuard(expectedKey: string | undefined, isPublic = false): ApiKeyGuard {
  const configService = { get: () => expectedKey } as unknown as ConfigService;
  const reflector = { getAllAndOverride: () => isPublic } as unknown as Reflector;
  return new ApiKeyGuard(configService, reflector);
}

function contextWithKey(apiKey?: string): ExecutionContext {
  const request = { headers: apiKey === undefined ? {} : { 'x-api-key': apiKey } };
  return {
    switchToHttp: () => ({ getRequest: () => request }),
    getHandler: () => null,
    getClass: () => null,
  } as unknown as ExecutionContext;
}

describe('ApiKeyGuard', () => {
  it('allows all requests when no key is configured (dev mode)', () => {
    const guard = makeGuard(undefined);
    expect(guard.canActivate(contextWithKey())).toBe(true);
  });

  it('allows @Public() routes even when a key is configured', () => {
    const guard = makeGuard('s3cret', true);
    expect(guard.canActivate(contextWithKey())).toBe(true);
  });

  it('rejects a missing key when one is configured', () => {
    const guard = makeGuard('s3cret');
    expect(() => guard.canActivate(contextWithKey())).toThrow(UnauthorizedException);
  });

  it('rejects a wrong key', () => {
    const guard = makeGuard('s3cret');
    expect(() => guard.canActivate(contextWithKey('nope'))).toThrow(UnauthorizedException);
  });

  it('rejects a key of different length without leaking via timing comparison', () => {
    const guard = makeGuard('s3cret');
    expect(() => guard.canActivate(contextWithKey('s3'))).toThrow(UnauthorizedException);
  });

  it('accepts the correct key', () => {
    const guard = makeGuard('s3cret');
    expect(guard.canActivate(contextWithKey('s3cret'))).toBe(true);
  });
});
