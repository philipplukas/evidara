import type {
  CanActivate,
  ExecutionContext,
} from '@nestjs/common';
import { Injectable, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Reflector } from '@nestjs/core';
import type { Request } from 'express';
import { timingSafeEqual } from 'node:crypto';
import { IS_PUBLIC_KEY } from './public.decorator';

/**
 * API key guard for legal-search API.
 *
 * When `API_KEY` env var is set, all guarded routes require a valid
 * `X-API-Key` header. When unset, the guard is a no-op (dev mode).
 *
 * Applied globally via APP_GUARD but excluded from health endpoints
 * using the `@Public()` decorator.
 */
@Injectable()
export class ApiKeyGuard implements CanActivate {
  private readonly expectedKey: string | undefined;

  constructor(
    configService: ConfigService,
    private readonly reflector: Reflector,
  ) {
    this.expectedKey = configService.get<string>('API_KEY');
  }

  canActivate(context: ExecutionContext): boolean {
    // Check for @Public() decorator
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) return true;
    // No key configured → allow all (dev mode)
    if (!this.expectedKey) return true;

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
