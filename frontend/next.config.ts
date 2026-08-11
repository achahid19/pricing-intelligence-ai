import type { NextConfig } from "next";

// The Next.js server evaluates this rewrite itself, so "localhost" only
// works when frontend and backend run as processes on the same host. Inside
// Docker Compose, the backend is reached by its service name instead.
const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
      {
        source: "/uploads/:path*",
        destination: `${backendUrl}/uploads/:path*`,
      },
    ];
  },
  // Next.js's rewrite proxy resets the backend connection at a hardcoded
  // 30s by default (confirmed live: a slow AI call — some models take
  // 30-70s+ for native web search — gets a real ECONNRESET/"socket hang
  // up" from Next.js itself, well before the backend's own request
  // finishes, surfacing as a bare "Internal Server Error" with no
  // relation to anything the backend actually did). 120s covers every
  // AI-call path in this app with real headroom.
  experimental: {
    proxyTimeout: 120000,
  },
};

export default nextConfig;
