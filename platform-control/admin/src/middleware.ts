import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

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
  return NextResponse.rewrite(targetUrl);
}

export const config = {
  matcher: ["/api/platform-control/:path*"],
};
