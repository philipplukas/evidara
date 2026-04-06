import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy API calls to the BFF during local development.
  // The Orval-generated client uses relative URLs (/v1/...),
  // so Next.js rewrites route them to the NestJS API.
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3002";
    return [
      {
        source: "/v1/:path*",
        destination: `${apiBase}/v1/:path*`,
      },
    ];
  },
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
