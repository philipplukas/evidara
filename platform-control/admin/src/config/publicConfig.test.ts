import { describe, expect, it } from "vitest";
import { buildPublicConfig, DEFAULT_LEGAL_SEARCH_BASE_URL } from "./publicConfig";

describe("publicConfig", () => {
  describe("legalSearchBaseUrl", () => {
    it("falls back to the local default when unset", () => {
      expect(buildPublicConfig({}).legalSearchBaseUrl).toBe(DEFAULT_LEGAL_SEARCH_BASE_URL);
    });

    it("falls back when the value is only whitespace", () => {
      expect(buildPublicConfig({ NEXT_PUBLIC_LEGAL_SEARCH_URL: "   " }).legalSearchBaseUrl).toBe(
        DEFAULT_LEGAL_SEARCH_BASE_URL,
      );
    });

    it("trims surrounding whitespace from the configured value", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_LEGAL_SEARCH_URL: "  https://ls.example/  " })
          .legalSearchBaseUrl,
      ).toBe("https://ls.example/");
    });
  });

  describe("legalSearchBaseUrlOrUndefined", () => {
    it("is undefined when unset (distinguishing unconfigured from default)", () => {
      expect(buildPublicConfig({}).legalSearchBaseUrlOrUndefined).toBeUndefined();
    });

    it("is undefined when whitespace-only", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_LEGAL_SEARCH_URL: "   " }).legalSearchBaseUrlOrUndefined,
      ).toBeUndefined();
    });

    it("returns the trimmed value when configured", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_LEGAL_SEARCH_URL: "  https://ls.example/  " })
          .legalSearchBaseUrlOrUndefined,
      ).toBe("https://ls.example/");
    });
  });

  describe("defaultUserRole", () => {
    it("is undefined when unset", () => {
      expect(buildPublicConfig({}).defaultUserRole).toBeUndefined();
    });

    it("returns the raw value untrimmed so `normalizeRole` owns normalization", () => {
      expect(buildPublicConfig({ NEXT_PUBLIC_USER_ROLE: "  Admin " }).defaultUserRole).toBe(
        "  Admin ",
      );
    });
  });

  describe("adminAllowedRoles", () => {
    it("defaults to ['admin'] when unset", () => {
      expect(buildPublicConfig({}).adminAllowedRoles).toEqual(["admin"]);
    });

    it("splits, trims, and lowercases comma-separated values", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "Admin, Operator ,VIEWER" })
          .adminAllowedRoles,
      ).toEqual(["admin", "operator", "viewer"]);
    });

    it("filters empty entries produced by trailing or duplicate commas", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "admin, ,,operator," })
          .adminAllowedRoles,
      ).toEqual(["admin", "operator"]);
    });

    it("returns an empty list when the env var is explicitly empty (?? treats '' as set)", () => {
      // Preserves the historical `parseAllowedRoles(env ?? "admin")` behavior:
      // an explicit empty string keeps the empty list, which the consumer
      // interprets as "allow all" via its `effectiveAllowedRoles` fallback.
      expect(buildPublicConfig({ NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "" }).adminAllowedRoles).toEqual(
        [],
      );
    });

    it("returns an empty list when the env var contains only separators/whitespace", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: " , , " }).adminAllowedRoles,
      ).toEqual([]);
    });
  });
});
