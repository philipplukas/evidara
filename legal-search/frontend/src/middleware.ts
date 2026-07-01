import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { publicConfig } from "@/config/publicConfig";

const DEV_API_URL = "https://legal-search-api-dev-kxc5agexna-oa.a.run.app";
const STAGING_API_URL = "https://legal-search-api-staging-kxc5agexna-oa.a.run.app";

function resolveApiBase(hostname: string): string {
  if (hostname.includes("legal-search-frontend-staging")) {
    return STAGING_API_URL;
  }
  if (hostname.includes("legal-search-frontend-dev")) {
    return DEV_API_URL;
  }
  // publicConfig.apiBaseUrl already applies the http://localhost:3102 default
  // via DEFAULT_API_BASE_URL when NEXT_PUBLIC_API_URL is unset.
  return publicConfig.apiBaseUrl;
}

export function middleware(request: NextRequest) {
  if (!request.nextUrl.pathname.startsWith("/v1/")) {
    return NextResponse.next();
  }

  const apiBase = resolveApiBase(request.nextUrl.hostname);
  const targetUrl = new URL(request.nextUrl.pathname + request.nextUrl.search, apiBase);

  // BFF auth (ADR-0020): inject the legal-search API key server-side so the browser
  // never sees it and the API can enforce X-API-Key. No-op when unset (API stays
  // open), so this is backward compatible.
  const requestHeaders = new Headers(request.headers);
  const apiKey = process.env.LEGAL_SEARCH_API_KEY;
  if (apiKey) {
    requestHeaders.set("X-API-Key", apiKey);
  }
  return NextResponse.rewrite(targetUrl, { request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/v1/:path*"],
};
