import { describe, expect, it } from "vitest";
import {
  buildControlPanelHref,
  CONTROL_PLANE_ITEM_PARAM,
  CONTROL_PLANE_ORIGIN_PARAM,
  CONTROL_PLANE_QUERY_PARAM,
  CONTROL_PLANE_RETURN_TO_PARAM,
  CONTROL_PLANE_SCOPE_PARAM,
  computeShowControlPlaneEntry,
} from "@/lib/control-plane-entry";

describe("computeShowControlPlaneEntry", () => {
  it("returns false when no control panel URL is configured", () => {
    expect(
      computeShowControlPlaneEntry({
        controlPanelUrl: undefined,
        cookieProfile: undefined,
        envDefaultProfile: "admin",
      }),
    ).toBe(false);
  });

  it("returns true for admin default when URL is set and no cookie", () => {
    expect(
      computeShowControlPlaneEntry({
        controlPanelUrl: "https://ops.example/admin",
        cookieProfile: undefined,
        envDefaultProfile: undefined,
      }),
    ).toBe(true);
  });

  it("returns false for standard default when URL is set and no cookie", () => {
    expect(
      computeShowControlPlaneEntry({
        controlPanelUrl: "https://ops.example/admin",
        cookieProfile: undefined,
        envDefaultProfile: "standard",
      }),
    ).toBe(false);
  });

  it("hides entry when cookie is standard even if env default is admin", () => {
    expect(
      computeShowControlPlaneEntry({
        controlPanelUrl: "https://ops.example/admin",
        cookieProfile: "standard",
        envDefaultProfile: "admin",
      }),
    ).toBe(false);
  });

  it("shows entry when cookie is admin even if env default is standard", () => {
    expect(
      computeShowControlPlaneEntry({
        controlPanelUrl: "https://ops.example/admin",
        cookieProfile: "admin",
        envDefaultProfile: "standard",
      }),
    ).toBe(true);
  });

  it("treats operator as admin", () => {
    expect(
      computeShowControlPlaneEntry({
        controlPanelUrl: "https://ops.example/admin",
        cookieProfile: "operator",
        envDefaultProfile: "standard",
      }),
    ).toBe(true);
  });

  it("denies unknown cookie values", () => {
    expect(
      computeShowControlPlaneEntry({
        controlPanelUrl: "https://ops.example/admin",
        cookieProfile: "superuser",
        envDefaultProfile: "admin",
      }),
    ).toBe(false);
  });
});

describe("buildControlPanelHref", () => {
  it("adds namespaced legal-search handoff context", () => {
    const href = buildControlPanelHref({
      controlPanelUrl: "https://ops.example/admin",
      returnTo: "https://search.example/?q=Art%20754%20OR&item=doc-1",
      query: "Art 754 OR",
      scopeLabel: 'Results for "Art 754 OR"',
      selectedId: "doc-1",
    });

    expect(href).toBeDefined();
    const url = new URL(href!);
    expect(`${url.origin}${url.pathname}`).toBe("https://ops.example/admin");
    expect(url.searchParams.get(CONTROL_PLANE_ORIGIN_PARAM)).toBe("legal-search");
    expect(url.searchParams.get(CONTROL_PLANE_RETURN_TO_PARAM)).toBe(
      "https://search.example/?q=Art%20754%20OR&item=doc-1",
    );
    expect(url.searchParams.get(CONTROL_PLANE_QUERY_PARAM)).toBe("Art 754 OR");
    expect(url.searchParams.get(CONTROL_PLANE_SCOPE_PARAM)).toBe('Results for "Art 754 OR"');
    expect(url.searchParams.get(CONTROL_PLANE_ITEM_PARAM)).toBe("doc-1");
  });

  it("returns undefined when the control panel URL is missing", () => {
    expect(
      buildControlPanelHref({
        controlPanelUrl: undefined,
        returnTo: "https://search.example/",
      }),
    ).toBeUndefined();
  });
});
