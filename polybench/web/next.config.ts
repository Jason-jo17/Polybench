import type { NextConfig } from "next";

// Where the dashboard proxies /api requests. Rewrites are resolved when the app
// is built, so for a production build set this at build time (the Docker image
// takes it as the POLYBENCH_API_URL build argument). NEXT_PUBLIC_API_URL is
// still honoured for older setups.
const apiUrl =
  process.env.POLYBENCH_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8080";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
