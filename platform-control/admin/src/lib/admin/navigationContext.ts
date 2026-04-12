"use client";

const HANDOFF_ORIGIN_PARAM = "from";
const HANDOFF_RETURN_TO_PARAM = "ls_return_to";
const HANDOFF_QUERY_PARAM = "ls_query";
const HANDOFF_SCOPE_PARAM = "ls_scope";
const HANDOFF_ITEM_PARAM = "ls_item";

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

export function resolveLegalSearchHandoff(
  searchParams: Pick<URLSearchParams, "get"> | null,
  fallbackUrl: string,
): LegalSearchHandoff {
  const rawReturnTo = normalizeValue(searchParams?.get(HANDOFF_RETURN_TO_PARAM) ?? null);
  const fallbackOrigin =
    typeof window !== "undefined" ? window.location.origin : "http://localhost";

  let returnToUrl = fallbackUrl;
  if (rawReturnTo) {
    try {
      const parsed = new URL(rawReturnTo, fallbackOrigin);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        returnToUrl = parsed.toString();
      }
    } catch {
      returnToUrl = fallbackUrl;
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
