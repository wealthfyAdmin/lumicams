/** @type {import('next').NextConfig} */
const BACKEND =
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.BACKEND_URL ||
  "http://localhost:8000";

const nextConfig = {
  // Smaller Node image for Docker (`frontend/Dockerfile`); safe for `next dev` / `next build`.
  output: "standalone",
  // Allow images served from the FastAPI backend (common dev ports)
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/snapshots/**",
      },
      {
        protocol: "http",
        hostname: "localhost",
        port: "8001",
        pathname: "/snapshots/**",
      },
      {
        protocol: "http",
        hostname: "127.0.0.1",
        port: "8000",
        pathname: "/snapshots/**",
      },
      {
        protocol: "http",
        hostname: "127.0.0.1",
        port: "8001",
        pathname: "/snapshots/**",
      },
    ],
  },
  // Proxy API + WebSocket + snapshots to FastAPI (must match backend port).
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${BACKEND}/ws/:path*`,
      },
      {
        source: "/snapshots/:path*",
        destination: `${BACKEND}/snapshots/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
