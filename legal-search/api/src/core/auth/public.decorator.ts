import { SetMetadata } from '@nestjs/common';

/**
 * Decorator to mark a route as public (no API key required).
 * Used on health endpoints that must remain unauthenticated.
 */
export const IS_PUBLIC_KEY = 'isPublic';
export const Public = () => SetMetadata(IS_PUBLIC_KEY, true);
