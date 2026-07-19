import type { ExecutionContext } from '@nestjs/common';
import { ServiceUnavailableException, UnauthorizedException } from '@nestjs/common';
import type { ConfigService } from '@nestjs/config';
import type { Reflector } from '@nestjs/core';
import { describe, expect, it } from 'vitest';
import { ApiKeyGuard } from './api-key.guard';

function makeGuard(
  expectedKey: string | undefined,
  isPublic = false,
  devAllowUnauthenticated: string | undefined = undefined,
): ApiKeyGuard {
  const configService = {
    get: (name: string) => (name === 'API_KEY' ? expectedKey : devAllowUnauthenticated),
  } as unknown as ConfigService;
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
  it('fails CLOSED when no key is configured and dev mode was not opted into', () => {
    // The regression that matters: this used to `return true` for every request, so a
    // deployment with an unmounted API_KEY served the whole API to anyone who could
    // reach it, indistinguishably from a correctly configured one.
    const guard = makeGuard(undefined);
    expect(() => guard.canActivate(contextWithKey())).toThrow(ServiceUnavailableException);
  });

  it('treats an empty-string API_KEY as unset rather than as a usable secret', () => {
    const guard = makeGuard('');
    expect(() => guard.canActivate(contextWithKey())).toThrow(ServiceUnavailableException);
  });

  it('keeps the keyless dev path when AUTH_DEV_ALLOW_UNAUTHENTICATED is set', () => {
    const guard = makeGuard(undefined, false, '1');
    expect(guard.canActivate(contextWithKey())).toBe(true);
  });

  it('ignores the dev flag once a key is configured, so it is not a backdoor', () => {
    const guard = makeGuard('s3cret', false, '1');
    expect(() => guard.canActivate(contextWithKey())).toThrow(UnauthorizedException);
    expect(guard.canActivate(contextWithKey('s3cret'))).toBe(true);
  });

  it('leaves @Public() health probes reachable on an unconfigured deployment', () => {
    // An unconfigured pod must still be diagnosable and must not fail its readiness probe.
    const guard = makeGuard(undefined, true);
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
