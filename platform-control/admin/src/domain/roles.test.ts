import { describe, expect, it } from "vitest";
import { Role } from "./roles";

describe("Role", () => {
  it("preserves the exact string values the access-control layer compares against", () => {
    // Role values are compared case-insensitively after normalizeRole —
    // keeping the constants lowercase guarantees Role.X === normalizeRole(Role.X).
    expect(Role.Admin).toBe("admin");
  });

  it("uses only lowercase values so normalizeRole is idempotent", () => {
    for (const value of Object.values(Role)) {
      expect(value).toBe(value.toLowerCase());
    }
  });
});
