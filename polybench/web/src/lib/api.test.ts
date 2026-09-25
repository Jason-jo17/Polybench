import { afterEach, describe, expect, it, vi } from "vitest";
import { api, humanize, isActive, pct, relativeTime, shortId } from "./api";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("formatting", () => {
  it("formats scores as percentages", () => {
    expect(pct(0.6428)).toBe("64.3%");
    expect(pct(1, 0)).toBe("100%");
    expect(pct(null)).toBe("0.0%");
  });

  it("shortens IDs and humanizes failure kinds", () => {
    expect(shortId("968361a3e4d9406181b74b87c58dd409")).toBe("968361a3");
    expect(humanize("wrong_output")).toBe("wrong output");
  });

  it("treats queued and running runs as active", () => {
    expect(isActive("PENDING")).toBe(true);
    expect(isActive("RUNNING")).toBe(true);
    expect(isActive("COMPLETED")).toBe(false);
    expect(isActive("FAILED")).toBe(false);
  });
});

describe("relativeTime", () => {
  it("reads the API's naive timestamps as UTC", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-25T12:00:00Z"));
    // Naive (no zone) means UTC: 2 hours ago, whatever the machine's time zone.
    expect(relativeTime("2026-09-25T10:00:00")).toBe("2 h ago");
    // Explicit offsets are respected.
    expect(relativeTime("2026-09-25T11:30:00+00:00")).toBe("30 min ago");
    expect(relativeTime("2026-09-25T11:59:30Z")).toBe("just now");
    expect(relativeTime("2026-09-22T12:00:00")).toBe("3 d ago");
  });
});

describe("api()", () => {
  it("returns the parsed body and prefixes /api", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/stats")).resolves.toEqual({ ok: 1 });
    expect(fetchMock).toHaveBeenCalledWith("/api/stats", undefined);
  });

  it("surfaces the API's detail message on errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "No tasks match." }), { status: 400 })),
    );
    await expect(api("/runs", { method: "POST" })).rejects.toThrow("No tasks match.");
  });

  it("falls back to the status code when the error body isn't JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { status: 502 })));
    await expect(api("/stats")).rejects.toThrow("The API returned 502 for /stats.");
  });
});
