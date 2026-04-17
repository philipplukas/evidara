"use client";

const HANDOFF_ORIGIN_PARAM = "from";
const HANDOFF_RETURN_TO_PARAM = "ls_return_to";
const HANDOFF_QUERY_PARAM = "ls_query";
const HANDOFF_SCOPE_PARAM = "ls_scope";
const HANDOFF_ITEM_PARAM = "ls_item";
const ALLOWED_PROTOCOLS = new Set(["http:", "https:"]);
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

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

function normalizePort(url: URL): string {
  if (url.port) {
    return url.port;
  }
  return url.protocol === "https:" ? "443" : "80";
}

function isLoopbackHost(hostname: string): boolean {
  return LOOPBACK_HOSTS.has(hostname);
}

function isAllowedReturnTarget(candidate: URL, configuredOrigin: string): boolean {
  if (candidate.origin === configuredOrigin) {
    return true;
  }

  try {
    const configured = new URL(configuredOrigin);
    return (
      candidate.protocol === configured.protocol &&
      normalizePort(candidate) === normalizePort(configured) &&
      isLoopbackHost(candidate.hostname) &&
      isLoopbackHost(configured.hostname)
    );
  } catch {
    return false;
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
      if (
        ALLOWED_PROTOCOLS.has(parsed.protocol) &&
        isAllowedReturnTarget(parsed, configuredOrigin)
      ) {
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

const LEGAL_SEARCH_FALLBACK_URL =
  process.env.NEXT_PUBLIC_LEGAL_SEARCH_URL?.trim() || "http://localhost:3101";

export function readLegalSearchHandoff(): LegalSearchHandoff {
  const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  return resolveLegalSearchHandoff(params, LEGAL_SEARCH_FALLBACK_URL);
}

export function describeLegalSearchHandoff(handoff: LegalSearchHandoff): string {
  const parts: string[] = [];

  if (handoff.scopeLabel) {
    parts.push(handoff.scopeLabel);
  }
  if (handoff.query) {
    parts.push(`Search "${handoff.query}"`);
  }
  if (handoff.selectedId) {
    parts.push(`Selected item: ${handoff.selectedId}`);
  }

  if (parts.length > 0) {
    return parts.join(" · ");
  }
  return "Continue from legal search";
}
