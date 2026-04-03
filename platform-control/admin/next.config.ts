import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    const apiBaseEnv = process.env.PLATFORM_CONTROL_API_URL;
    if (!apiBaseEnv && process.env.NODE_ENV === "production") {
      throw new Error("PLATFORM_CONTROL_API_URL must be set in production");
    }
    const apiBase = apiBaseEnv ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/platform-control/:path*",
        destination: `${apiBase}/:path*`,
      },
    ];
  },
};

export default nextConfig;
