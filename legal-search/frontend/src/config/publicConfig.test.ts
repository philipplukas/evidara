import { describe, expect, it } from "vitest";
import { buildPublicConfig, DEFAULT_API_BASE_URL } from "@/config/publicConfig";

describe("buildPublicConfig", () => {
  it("applies defaults when no env vars are set", () => {
    const cfg = buildPublicConfig({});
    expect(cfg.apiBaseUrl).toBe(DEFAULT_API_BASE_URL);
    expect(cfg.controlPanelBaseUrl).toBeUndefined();
    expect(cfg.defaultUiProfile).toBeUndefined();
    expect(cfg.docsBaseUrl).toBeUndefined();
  });

  it("uses the explicit NEXT_PUBLIC_API_URL when provided", () => {
    const cfg = buildPublicConfig({ NEXT_PUBLIC_API_URL: "https://api.example.com" });
    expect(cfg.apiBaseUrl).toBe("https://api.example.com");
  });

  it("trims whitespace around string values", () => {
    const cfg = buildPublicConfig({
      NEXT_PUBLIC_API_URL: "  https://api.example.com  ",
      NEXT_PUBLIC_CONTROL_PANEL_URL: "  https://ops.example/admin  ",
      NEXT_PUBLIC_DEFAULT_UI_PROFILE: "  admin  ",
    });
    expect(cfg.apiBaseUrl).toBe("https://api.example.com");
    expect(cfg.controlPanelBaseUrl).toBe("https://ops.example/admin");
    expect(cfg.defaultUiProfile).toBe("admin");
  });

  it("treats empty/whitespace-only strings as unset", () => {
    const cfg = buildPublicConfig({
      NEXT_PUBLIC_API_URL: "   ",
      NEXT_PUBLIC_CONTROL_PANEL_URL: "",
      NEXT_PUBLIC_DEFAULT_UI_PROFILE: "\t\n",
      NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL: "   ",
    });
    expect(cfg.apiBaseUrl).toBe(DEFAULT_API_BASE_URL);
    expect(cfg.controlPanelBaseUrl).toBeUndefined();
    expect(cfg.defaultUiProfile).toBeUndefined();
    expect(cfg.docsBaseUrl).toBeUndefined();
  });

  it("strips a single trailing slash from the docs base URL", () => {
    const cfg = buildPublicConfig({
      NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL: "https://docs.example.com/",
    });
    expect(cfg.docsBaseUrl).toBe("https://docs.example.com");
  });

  it("leaves docs base URL without a trailing slash untouched", () => {
    const cfg = buildPublicConfig({
      NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL: "https://docs.example.com",
    });
    expect(cfg.docsBaseUrl).toBe("https://docs.example.com");
  });
});
