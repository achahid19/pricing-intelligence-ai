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
};

export default nextConfig;
