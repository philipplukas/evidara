import { afterEach, describe, expect, it, vi } from "vitest";
import { customFetch, parseApiResponseBody } from "./custom-fetch";

describe("customFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("parses json bodies when available", () => {
    expect(parseApiResponseBody('{"ok":true}')).toEqual({ ok: true });
  });

  it("falls back to a detail object for plain-text bodies", () => {
    expect(parseApiResponseBody("Internal Server Error")).toEqual({
      detail: "Internal Server Error",
    });
  });

  it("returns a non-200 response payload without throwing on plain-text errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 500,
        headers: new Headers(),
        text: vi.fn().mockResolvedValue("Internal Server Error"),
      }),
    );

    const response = await customFetch<{ data: { detail: string }; status: number }>(
      "/v1/search/context",
      { method: "GET" },
    );

    expect(response.status).toBe(500);
    expect(response.data).toEqual({ detail: "Internal Server Error" });
  });
});
