import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    const apiBase = process.env.PLATFORM_CONTROL_API_URL ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/platform-control/:path*",
        destination: `${apiBase}/:path*`,
      },
    ];
  },
};

export default nextConfig;
