/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // d3-force-3d is ESM-only; tell Next.js to transpile it for the browser bundle.
  transpilePackages: ["d3-force-3d"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
