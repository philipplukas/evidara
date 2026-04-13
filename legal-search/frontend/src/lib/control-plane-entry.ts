/** Cookie set by auth/session integration; E2E may set it for contract tests. */
export const EVIDARA_UI_PROFILE_COOKIE = "evidara-ui-profile";
export const CONTROL_PLANE_ORIGIN_PARAM = "from";
export const CONTROL_PLANE_RETURN_TO_PARAM = "ls_return_to";
export const CONTROL_PLANE_QUERY_PARAM = "ls_query";
export const CONTROL_PLANE_SCOPE_PARAM = "ls_scope";
export const CONTROL_PLANE_ITEM_PARAM = "ls_item";

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

export function buildControlPanelHref(options: {
  controlPanelUrl: string | undefined;
  returnTo: string | undefined;
  query?: string;
  scopeLabel?: string;
  selectedId?: string | null;
}): string | undefined {
  const panelUrl = options.controlPanelUrl?.trim();
  if (!panelUrl) {
    return undefined;
  }

  try {
    const url = new URL(
      panelUrl,
      typeof window !== "undefined" ? window.location.origin : "http://localhost",
    );

    url.searchParams.set(CONTROL_PLANE_ORIGIN_PARAM, "legal-search");

    const returnTo = options.returnTo?.trim();
    if (returnTo) {
      url.searchParams.set(CONTROL_PLANE_RETURN_TO_PARAM, returnTo);
    }

    const query = options.query?.trim();
    if (query) {
      url.searchParams.set(CONTROL_PLANE_QUERY_PARAM, query);
    }

    const scopeLabel = options.scopeLabel?.trim();
    if (scopeLabel) {
      url.searchParams.set(CONTROL_PLANE_SCOPE_PARAM, scopeLabel);
    }

    const selectedId = options.selectedId?.trim();
    if (selectedId) {
      url.searchParams.set(CONTROL_PLANE_ITEM_PARAM, selectedId);
    }

    return url.toString();
  } catch {
    return panelUrl;
  }
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
