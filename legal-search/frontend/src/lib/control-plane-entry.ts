/** Cookie set by auth/session integration; E2E may set it for contract tests. */
export const EVIDARA_UI_PROFILE_COOKIE = "evidara-ui-profile";

export type UiProfile = "admin" | "standard";

/**
 * Whether the legal-search header should expose the control-plane entrypoint.
 * URL must be configured; profile must be admin (explicit or default).
 */
export function computeShowControlPlaneEntry(options: {
  controlPanelUrl: string | undefined;
  cookieProfile: string | undefined;
  envDefaultProfile: string | undefined;
}): boolean {
  const panelUrl = options.controlPanelUrl?.trim();
  if (!panelUrl) {
    return false;
  }

  const envDefault = normalizeProfile(options.envDefaultProfile) ?? "admin";
  const fromCookie = options.cookieProfile?.trim();

  if (fromCookie) {
    const p = normalizeProfile(fromCookie);
    if (p === "standard") {
      return false;
    }
    if (p === "admin") {
      return true;
    }
    return false;
  }

  return envDefault === "admin";
}

function normalizeProfile(value: string | undefined): UiProfile | undefined {
  if (!value?.trim()) {
    return undefined;
  }
  const v = value.trim().toLowerCase();
  if (v === "admin" || v === "operator") {
    return "admin";
  }
  if (v === "standard" || v === "user" || v === "non-admin") {
    return "standard";
  }
  return undefined;
}
