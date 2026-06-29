import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const DEV_API_URL = "https://platform-control-api-dev-kxc5agexna-oa.a.run.app";
const STAGING_API_URL = "https://platform-control-api-staging-kxc5agexna-oa.a.run.app";
const LOCAL_API_URL = "http://127.0.0.1:8000";

function resolveApiBase(hostname: string): string {
  if (hostname.includes("platform-control-admin-staging")) {
    return STAGING_API_URL;
  }
  if (hostname.includes("platform-control-admin-dev")) {
    return DEV_API_URL;
  }
  return process.env.PLATFORM_CONTROL_API_URL ?? LOCAL_API_URL;
}

export function middleware(request: NextRequest) {
  if (!request.nextUrl.pathname.startsWith("/api/platform-control/")) {
    return NextResponse.next();
  }

  const apiBase = resolveApiBase(request.nextUrl.hostname);
  const path = request.nextUrl.pathname.replace("/api/platform-control", "");
  const targetUrl = new URL(path + request.nextUrl.search, apiBase);

  // BFF auth (ADR-0020): inject the operator API key server-side so the browser
  // never sees it and platform-control can enforce X-API-Key. No-op when unset
  // (API stays open), so this is backward compatible.
  const requestHeaders = new Headers(request.headers);
  const operatorApiKey = process.env.PLATFORM_CONTROL_OPERATOR_API_KEY;
  if (operatorApiKey) {
    requestHeaders.set("X-API-Key", operatorApiKey);
  }
  return NextResponse.rewrite(targetUrl, { request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/api/platform-control/:path*"],
};
