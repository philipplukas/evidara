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
