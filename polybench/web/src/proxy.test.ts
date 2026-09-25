// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { proxy } from "./proxy";

const request = (auth?: string) =>
  new NextRequest("http://localhost:3000/runs", auth ? { headers: { authorization: auth } } : undefined);
const basic = (user: string, password: string) =>
  `Basic ${Buffer.from(`${user}:${password}`).toString("base64")}`;

afterEach(() => vi.unstubAllEnvs());

describe("dashboard password", () => {
  it("lets everything through when no password is set", () => {
    vi.stubEnv("POLYBENCH_DASHBOARD_PASSWORD", "");
    expect(proxy(request()).status).toBe(200);
  });

  it("asks for credentials when a password is set", () => {
    vi.stubEnv("POLYBENCH_DASHBOARD_PASSWORD", "s3cret");
    const res = proxy(request());
    expect(res.status).toBe(401);
    expect(res.headers.get("WWW-Authenticate")).toContain("Basic");
  });

  it("accepts the right password with any username, and rejects wrong ones", () => {
    vi.stubEnv("POLYBENCH_DASHBOARD_PASSWORD", "s3cret");
    expect(proxy(request(basic("anyone", "s3cret"))).status).toBe(200);
    expect(proxy(request(basic("anyone", "wrong"))).status).toBe(401);
    expect(proxy(request(basic("anyone", "s3cret-longer"))).status).toBe(401);
    expect(proxy(request("Bearer s3cret")).status).toBe(401);
  });

  it("allows colons in the password", () => {
    vi.stubEnv("POLYBENCH_DASHBOARD_PASSWORD", "a:b:c");
    expect(proxy(request(basic("user", "a:b:c"))).status).toBe(200);
  });
});
