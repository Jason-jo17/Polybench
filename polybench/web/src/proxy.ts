import { NextRequest, NextResponse } from "next/server";

export function proxy(req: NextRequest) {
  const basicAuth = req.headers.get("authorization");
  const dashboardPassword = process.env.POLYBENCH_DASHBOARD_PASSWORD;

  if (dashboardPassword) {
    if (basicAuth) {
      const authValue = basicAuth.split(" ")[1];
      if (authValue) {
        // Decode base64: Basic auth string is username:password
        const decoded = Buffer.from(authValue, "base64").toString();
        // Since we don't care about the username, just get the password
        // The format is username:password. It might have multiple colons if the password has colons,
        // so we split by the first colon.
        const firstColonIndex = decoded.indexOf(':');
        const password = firstColonIndex !== -1 ? decoded.substring(firstColonIndex + 1) : decoded;

        if (password === dashboardPassword) {
          return NextResponse.next();
        }
      }
    }

    return new NextResponse("Authentication required", {
      status: 401,
      headers: {
        "WWW-Authenticate": 'Basic realm="PolyBench Dashboard"',
      },
    });
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
