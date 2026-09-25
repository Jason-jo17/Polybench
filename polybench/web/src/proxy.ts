import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

// HTTP basic auth for the dashboard, enabled by POLYBENCH_DASHBOARD_PASSWORD.
// Any username is accepted. The browser also sends these credentials with its
// /api requests, which the backend checks against the same password.
// Proxy runs on the Node.js runtime, so the password is read when the server
// starts, not baked in at build time.

function passwordMatches(header: string | null, expected: string): boolean {
  const [scheme, encoded] = header?.split(" ") ?? [];
  if (scheme !== "Basic" || !encoded) return false;
  const decoded = Buffer.from(encoded, "base64").toString();
  // Passwords may contain colons, so split on the first one only.
  const password = decoded.slice(decoded.indexOf(":") + 1);
  const a = Buffer.from(password);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export function proxy(req: NextRequest) {
  const expected = process.env.POLYBENCH_DASHBOARD_PASSWORD;
  if (!expected || passwordMatches(req.headers.get("authorization"), expected)) {
    return NextResponse.next();
  }
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="PolyBench Dashboard"' },
  });
}

export const config = {
  // Everything except static assets and the favicon.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
