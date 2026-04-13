"use client";

const HANDOFF_ORIGIN_PARAM = "from";
const HANDOFF_RETURN_TO_PARAM = "ls_return_to";
const HANDOFF_QUERY_PARAM = "ls_query";
const HANDOFF_SCOPE_PARAM = "ls_scope";
const HANDOFF_ITEM_PARAM = "ls_item";
const ALLOWED_PROTOCOLS = new Set(["http:", "https:"]);

export type LegalSearchHandoff = {
  hasOrigin: boolean;
  returnToUrl: string;
  query?: string;
  scopeLabel?: string;
  selectedId?: string;
};

function normalizeValue(value: string | null): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function resolveConfiguredOrigin(fallbackUrl: string): string | null {
  try {
    const parsed = new URL(fallbackUrl);
    return ALLOWED_PROTOCOLS.has(parsed.protocol) ? parsed.origin : null;
  } catch {
    return null;
  }
}

export function resolveLegalSearchHandoff(
  searchParams: Pick<URLSearchParams, "get"> | null,
  fallbackUrl: string,
): LegalSearchHandoff {
  const rawReturnTo = normalizeValue(searchParams?.get(HANDOFF_RETURN_TO_PARAM) ?? null);
  const configuredOrigin =
    resolveConfiguredOrigin(fallbackUrl) ??
    (typeof window !== "undefined" ? window.location.origin : "http://localhost");

  let returnToUrl = fallbackUrl;
  if (rawReturnTo) {
    try {
      const parsed = new URL(rawReturnTo, configuredOrigin);
      if (ALLOWED_PROTOCOLS.has(parsed.protocol) && parsed.origin === configuredOrigin) {
        returnToUrl = parsed.toString();
      }
    } catch {
      // Keep the configured legal-search URL when the handoff target is malformed.
    }
  }

  return {
    hasOrigin: (searchParams?.get(HANDOFF_ORIGIN_PARAM) ?? "").trim() === "legal-search",
    returnToUrl,
    query: normalizeValue(searchParams?.get(HANDOFF_QUERY_PARAM) ?? null),
    scopeLabel: normalizeValue(searchParams?.get(HANDOFF_SCOPE_PARAM) ?? null),
    selectedId: normalizeValue(searchParams?.get(HANDOFF_ITEM_PARAM) ?? null),
  };
}

export function describeLegalSearchHandoff(handoff: LegalSearchHandoff): string {
  if (handoff.scopeLabel && handoff.query) {
    return `${handoff.scopeLabel} · Search "${handoff.query}"`;
  }
  if (handoff.scopeLabel) {
    return handoff.scopeLabel;
  }
  if (handoff.query) {
    return `Search "${handoff.query}"`;
  }
  return "Continue from legal search";
}
