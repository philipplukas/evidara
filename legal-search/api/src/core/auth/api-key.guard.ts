import { timingSafeEqual } from 'node:crypto';
import type { CanActivate, ExecutionContext } from '@nestjs/common';
import { Injectable, ServiceUnavailableException, UnauthorizedException } from '@nestjs/common';
// biome-ignore lint/style/useImportType: value import so NestJS DI resolves ConfigService at runtime
import { ConfigService } from '@nestjs/config';
// biome-ignore lint/style/useImportType: value import so NestJS DI resolves Reflector at runtime
import { Reflector } from '@nestjs/core';
import type { Request } from 'express';
import { IS_PUBLIC_KEY } from './public.decorator';

const TRUTHY = new Set(['1', 'true', 'yes', 'on']);

/**
 * API key guard for legal-search API.
 *
 * When `API_KEY` is set, all guarded routes require a valid `X-API-Key` header.
 *
 * When `API_KEY` is **unset** the guard fails **closed** (503) unless
 * `AUTH_DEV_ALLOW_UNAUTHENTICATED` is explicitly truthy. It used to `return true`
 * for everything, so a deployment that forgot to mount the key served the whole API
 * to anyone who could reach it — and nothing in the response distinguished that from
 * a correctly configured deployment. The open path still exists for local development;
 * it just has to be asked for by name now. See ADR-0020 and ADR-0038.
 *
 * Applied globally via APP_GUARD but excluded from health endpoints
 * using the `@Public()` decorator, so probes keep working either way.
 */
@Injectable()
export class ApiKeyGuard implements CanActivate {
  private readonly expectedKey: string | undefined;
  private readonly devAllowUnauthenticated: boolean;

  constructor(
    configService: ConfigService,
    private readonly reflector: Reflector,
  ) {
    this.expectedKey = configService.get<string>('API_KEY') || undefined;
    this.devAllowUnauthenticated = TRUTHY.has(
      (configService.get<string>('AUTH_DEV_ALLOW_UNAUTHENTICATED') ?? '').trim().toLowerCase(),
    );
  }

  canActivate(context: ExecutionContext): boolean {
    // Check for @Public() decorator
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) return true;

    // No key configured. Fail CLOSED unless the keyless dev path was opted into.
    if (!this.expectedKey) {
      if (this.devAllowUnauthenticated) return true;
      throw new ServiceUnavailableException(
        'Authentication is not configured. Set API_KEY, or opt into the keyless ' +
          'local-development path with AUTH_DEV_ALLOW_UNAUTHENTICATED=1.',
      );
    }

    const request = context.switchToHttp().getRequest<Request>();
    const apiKey = request.headers['x-api-key'] as string | undefined;

    if (!apiKey) {
      throw new UnauthorizedException('Missing API key');
    }

    // Timing-safe comparison to prevent timing attacks
    const expected = Buffer.from(this.expectedKey);
    const provided = Buffer.from(apiKey);
    if (expected.length !== provided.length || !timingSafeEqual(expected, provided)) {
      throw new UnauthorizedException('Invalid API key');
    }

    return true;
  }
}
