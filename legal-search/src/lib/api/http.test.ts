import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { httpClient } from "./http";

function makeFetchResponse(
  body: unknown,
  init: { ok: boolean; status: number; statusText: string } = {
    ok: true,
    status: 200,
    statusText: "OK",
  },
): Response {
  return {
    ok: init.ok,
    status: init.status,
    statusText: init.statusText,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

describe("httpClient", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("successful responses", () => {
    it("returns parsed JSON body on a 200 response", async () => {
      const payload = { id: "1", title: "Test" };
      vi.mocked(fetch).mockResolvedValue(makeFetchResponse(payload));

      const result = await httpClient<typeof payload>("/v1/search");

      expect(result).toEqual(payload);
    });

    it("calls fetch with the provided URL", async () => {
      vi.mocked(fetch).mockResolvedValue(makeFetchResponse({}));

      await httpClient("/bff/articles/42");

      expect(fetch).toHaveBeenCalledWith(
        "/bff/articles/42",
        expect.any(Object),
      );
    });

    it("always sets Content-Type: application/json header", async () => {
      vi.mocked(fetch).mockResolvedValue(makeFetchResponse({}));

      await httpClient("/v1/search");

      const [, options] = vi.mocked(fetch).mock.calls[0];
      expect((options?.headers as Record<string, string>)["Content-Type"]).toBe(
        "application/json",
      );
    });

    it("merges caller headers with the default Content-Type header", async () => {
      vi.mocked(fetch).mockResolvedValue(makeFetchResponse({}));

      await httpClient("/v1/search", {
        headers: { Authorization: "Bearer token123" },
      });

      const [, options] = vi.mocked(fetch).mock.calls[0];
      const headers = options?.headers as Record<string, string>;
      expect(headers["Content-Type"]).toBe("application/json");
      expect(headers["Authorization"]).toBe("Bearer token123");
    });

    it("allows caller to override the Content-Type header", async () => {
      vi.mocked(fetch).mockResolvedValue(makeFetchResponse({}));

      await httpClient("/v1/search", {
        headers: { "Content-Type": "text/plain" },
      });

      const [, options] = vi.mocked(fetch).mock.calls[0];
      const headers = options?.headers as Record<string, string>;
      expect(headers["Content-Type"]).toBe("text/plain");
    });

    it("forwards RequestInit options (method, body) to fetch", async () => {
      vi.mocked(fetch).mockResolvedValue(makeFetchResponse([]));

      const body = JSON.stringify({ query: "contracts" });
      await httpClient("/v1/search", { method: "POST", body });

      const [, options] = vi.mocked(fetch).mock.calls[0];
      expect(options?.method).toBe("POST");
      expect(options?.body).toBe(body);
    });

    it("works with no options argument (options is undefined)", async () => {
      vi.mocked(fetch).mockResolvedValue(makeFetchResponse({ ok: true }));

      await expect(httpClient("/bff/documents/1/summary")).resolves.toEqual({
        ok: true,
      });

      const [, options] = vi.mocked(fetch).mock.calls[0];
      expect(options?.method).toBeUndefined();
    });

    it("returns an array response correctly", async () => {
      const results = [
        { id: "a", type: "case", title: "T", subtitle: "S", snippet: "N" },
        { id: "b", type: "statute", title: "U", subtitle: "V", snippet: "W" },
      ];
      vi.mocked(fetch).mockResolvedValue(makeFetchResponse(results));

      const data = await httpClient<typeof results>("/v1/search");

      expect(data).toHaveLength(2);
      expect(data[0].id).toBe("a");
      expect(data[1].type).toBe("statute");
    });
  });

  describe("error responses", () => {
    it("throws an Error when the response is not ok (404)", async () => {
      vi.mocked(fetch).mockResolvedValue(
        makeFetchResponse(null, {
          ok: false,
          status: 404,
          statusText: "Not Found",
        }),
      );

      await expect(httpClient("/bff/articles/missing")).rejects.toThrow(
        "HTTP 404 Not Found",
      );
    });

    it("throws an Error when the response is not ok (500)", async () => {
      vi.mocked(fetch).mockResolvedValue(
        makeFetchResponse(null, {
          ok: false,
          status: 500,
          statusText: "Internal Server Error",
        }),
      );

      await expect(httpClient("/v1/search")).rejects.toThrow(
        "HTTP 500 Internal Server Error",
      );
    });

    it("throws an Error when the response is not ok (400)", async () => {
      vi.mocked(fetch).mockResolvedValue(
        makeFetchResponse(null, {
          ok: false,
          status: 400,
          statusText: "Bad Request",
        }),
      );

      await expect(httpClient("/v1/search")).rejects.toThrow(
        "HTTP 400 Bad Request",
      );
    });

    it("throws an Error when the response is not ok (401)", async () => {
      vi.mocked(fetch).mockResolvedValue(
        makeFetchResponse(null, {
          ok: false,
          status: 401,
          statusText: "Unauthorized",
        }),
      );

      await expect(httpClient("/bff/articles/1")).rejects.toThrow(
        "HTTP 401 Unauthorized",
      );
    });

    it("error message includes exact HTTP status code and status text", async () => {
      vi.mocked(fetch).mockResolvedValue(
        makeFetchResponse(null, {
          ok: false,
          status: 503,
          statusText: "Service Unavailable",
        }),
      );

      let thrownError: unknown;
      try {
        await httpClient("/v1/search");
      } catch (err) {
        thrownError = err;
      }

      expect(thrownError).toBeInstanceOf(Error);
      expect((thrownError as Error).message).toBe(
        "HTTP 503 Service Unavailable",
      );
    });

    it("does not call response.json() when response is not ok", async () => {
      const jsonSpy = vi.fn();
      vi.mocked(fetch).mockResolvedValue({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        json: jsonSpy,
      } as unknown as Response);

      await expect(httpClient("/v1/search")).rejects.toThrow();

      expect(jsonSpy).not.toHaveBeenCalled();
    });

    it("propagates network-level errors from fetch itself", async () => {
      vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));

      await expect(httpClient("/v1/search")).rejects.toThrow("Failed to fetch");
    });
  });
});