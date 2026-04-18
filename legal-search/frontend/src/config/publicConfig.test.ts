import { describe, expect, it } from "vitest";
import {
  buildPublicConfig,
  DEFAULT_API_BASE_URL,
  DEFAULT_LEGAL_SEARCH_BASE_URL,
} from "./publicConfig";

describe("publicConfig", () => {
  describe("apiBaseUrl", () => {
    it("falls back to the local default when NEXT_PUBLIC_API_URL is unset", () => {
      expect(buildPublicConfig({}).apiBaseUrl).toBe(DEFAULT_API_BASE_URL);
    });

    it("returns the configured value when set", () => {
      expect(buildPublicConfig({ NEXT_PUBLIC_API_URL: "https://api.example.com" }).apiBaseUrl).toBe(
        "https://api.example.com",
      );
    });

    it("accepts an empty string without falling back (preserves historical ?? behavior)", () => {
      // `??` treats empty string as set, so the call site would pass an
      // empty string through. The config module must preserve that.
      expect(buildPublicConfig({ NEXT_PUBLIC_API_URL: "" }).apiBaseUrl).toBe("");
    });
  });

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

  describe("controlPanelBaseUrl", () => {
    it("is undefined when unset", () => {
      expect(buildPublicConfig({}).controlPanelBaseUrl).toBeUndefined();
    });

    it("is undefined when whitespace-only", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_CONTROL_PANEL_URL: "   " }).controlPanelBaseUrl,
      ).toBeUndefined();
    });

    it("returns the trimmed URL when set", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_CONTROL_PANEL_URL: "  https://admin.example/  " })
          .controlPanelBaseUrl,
      ).toBe("https://admin.example/");
    });
  });

  describe("defaultUiProfile", () => {
    it("returns the raw value untrimmed so the consumer owns normalization", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_DEFAULT_UI_PROFILE: "  Admin  " }).defaultUiProfile,
      ).toBe("  Admin  ");
    });

    it("is undefined when unset", () => {
      expect(buildPublicConfig({}).defaultUiProfile).toBeUndefined();
    });
  });

  describe("docsBaseUrl", () => {
    it("is an empty string when unset", () => {
      expect(buildPublicConfig({}).docsBaseUrl).toBe("");
    });

    it("strips a single trailing slash from the configured value", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL: "https://docs.example/" })
          .docsBaseUrl,
      ).toBe("https://docs.example");
    });

    it("keeps the value intact when there is no trailing slash", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL: "https://docs.example" })
          .docsBaseUrl,
      ).toBe("https://docs.example");
    });

    it("preserves an empty string (no trailing slash to strip)", () => {
      expect(buildPublicConfig({ NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL: "" }).docsBaseUrl).toBe("");
    });
  });
});
