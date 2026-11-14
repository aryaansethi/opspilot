import type { NextConfig } from "next";

// Baseline browser hardening for every route. The app never needs to be framed, sniffed or to
// leak full URLs to other origins. (A full CSP would also need connect-src for the API origin,
// which differs between dev, Compose and any deployment, so it's left to the deployment.)
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image (frontend/Dockerfile). `next dev` is unaffected.
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
