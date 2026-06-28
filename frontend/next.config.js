/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // d3-force-3d is ESM-only; tell Next.js to transpile it for the browser bundle.
  transpilePackages: ["d3-force-3d"],
  async rewrites() {
    // BACKEND_URL is a server-side-only env var pointing at the actual backend process.
    // NEXT_PUBLIC_API_URL tells the browser client to route through /api/* (this proxy).
    // They must be set independently — using NEXT_PUBLIC_API_URL here caused a
    // localhost:3000 → localhost:3000 self-referencing loop and 404s.
    const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
  experimental: {
    proxyTimeout: 180000,
  },
};

module.exports = nextConfig;
