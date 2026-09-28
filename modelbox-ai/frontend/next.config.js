/** @type {import('next').NextConfig} */

// Where the Next.js server forwards /api/*. The browser only ever talks to
// the UI's own origin, so the backend needs no published port and no URL is
// inlined into the client bundle. This file is evaluated when the image is
// built, so the image carries the compose service name; MODELBOX_BACKEND_URL
// exists for `next dev` against a backend on localhost.
const BACKEND_URL = process.env.MODELBOX_BACKEND_URL ?? 'http://modelbox-backend:8000';

const nextConfig = {
  reactStrictMode: true,
  // Standalone output produces a minimal server bundle for the Docker image.
  output: 'standalone',
  async rewrites() {
    return [
      // The backend's liveness probe sits at /health, outside /api. Forwarding
      // it lets the appliance be monitored on its one published port. First,
      // because rewrites apply in order and the next one would claim it.
      { source: '/api/health', destination: `${BACKEND_URL}/health` },
      { source: '/api/:path*', destination: `${BACKEND_URL}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
