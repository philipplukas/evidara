import { describe, expect, it } from "vitest";
import { computeShowControlPlaneEntry } from "@/lib/control-plane-entry";

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
