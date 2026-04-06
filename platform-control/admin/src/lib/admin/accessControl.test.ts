import { describe, expect, it } from "vitest";
import { isRoleAuthorized, normalizeRole, parseAllowedRoles } from "./accessControl";

describe("accessControl", () => {
  it("normalizes role values", () => {
    expect(normalizeRole("  Admin ")).toBe("admin");
    expect(normalizeRole(undefined)).toBe("");
  });

  it("parses allowed roles list", () => {
    expect(parseAllowedRoles("admin, operator , viewer")).toEqual(["admin", "operator", "viewer"]);
    expect(parseAllowedRoles(undefined)).toEqual([]);
  });

  it("authorizes user role against allowed roles", () => {
    expect(isRoleAuthorized("admin", ["admin"])).toBe(true);
    expect(isRoleAuthorized("viewer", ["admin"])).toBe(false);
  });

  it("treats empty allowed-role config as allow-all", () => {
    expect(isRoleAuthorized("viewer", [])).toBe(true);
  });
});
