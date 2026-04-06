import { afterEach, describe, expect, it, vi } from "vitest";
import {
  isRoleAuthorized,
  normalizeRole,
  parseAllowedRoles,
  resolveUserRole,
} from "./accessControl";

describe("accessControl", () => {
  const originalWindow = globalThis.window;

  afterEach(() => {
    if (originalWindow === undefined) {
      Reflect.deleteProperty(globalThis, "window");
    } else {
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: originalWindow,
      });
    }
  });

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

  it("resolves role from localStorage override when present", () => {
    const getItem = vi.fn().mockReturnValue("operator");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: {
        localStorage: { getItem },
      },
    });

    expect(resolveUserRole("admin")).toBe("operator");
    expect(getItem).toHaveBeenCalledWith("evidara_user_role");
  });

  it("falls back to provided role when localStorage override is missing", () => {
    const getItem = vi.fn().mockReturnValue(null);
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: {
        localStorage: { getItem },
      },
    });

    expect(resolveUserRole("admin")).toBe("admin");
    expect(getItem).toHaveBeenCalledWith("evidara_user_role");
  });
});
