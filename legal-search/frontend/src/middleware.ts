import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const DEV_API_URL = "https://legal-search-api-dev-kxc5agexna-oa.a.run.app";
const STAGING_API_URL = "https://legal-search-api-staging-kxc5agexna-oa.a.run.app";
const LOCAL_API_URL = "http://localhost:3002";

function resolveApiBase(hostname: string): string {
  if (hostname.includes("legal-search-frontend-staging")) {
    return STAGING_API_URL;
  }
  if (hostname.includes("legal-search-frontend-dev")) {
    return DEV_API_URL;
  }
  return process.env.NEXT_PUBLIC_API_URL ?? LOCAL_API_URL;
}

export function middleware(request: NextRequest) {
  if (!request.nextUrl.pathname.startsWith("/v1/")) {
    return NextResponse.next();
  }

  const apiBase = resolveApiBase(request.nextUrl.hostname);
  const targetUrl = new URL(request.nextUrl.pathname + request.nextUrl.search, apiBase);
  return NextResponse.rewrite(targetUrl);
}

export const config = {
  matcher: ["/v1/:path*"],
};
