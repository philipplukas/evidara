import { Role } from "../../domain/roles";

export function normalizeRole(value: string | undefined): string {
  return value?.trim().toLowerCase() ?? "";
}

export function parseAllowedRoles(value: string | undefined): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((entry) => normalizeRole(entry))
    .filter(Boolean);
}

export function resolveUserRole(fallbackRole: string): string {
  if (typeof window === "undefined") return fallbackRole;
  const localOverride = normalizeRole(
    window.localStorage.getItem("evidara_user_role") ?? undefined,
  );
  return localOverride || fallbackRole;
}

export function isRoleAuthorized(userRole: string, allowedRoles: string[]): boolean {
  if (allowedRoles.length === 0) return true;
  return allowedRoles.includes(userRole);
}

/**
 * Default allowed roles for admin surfaces when neither the operator nor
 * the deployment has overridden `NEXT_PUBLIC_ADMIN_ALLOWED_ROLES`. Centralised
 * here so callers go through the `Role` union rather than the raw string.
 */
export const DEFAULT_ADMIN_ALLOWED_ROLES: ReadonlyArray<Role> = [Role.Admin];
