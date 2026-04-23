import { describe, expect, it } from "vitest";
import { type AdminStatusLevel, adminLevelBorder } from "./StatusBadge";

describe("adminLevelBorder", () => {
  it("derives every status border from the shared --status-* / --border-strong tokens", () => {
    const levels: AdminStatusLevel[] = ["healthy", "degraded", "critical", "neutral", "info"];
    for (const level of levels) {
      expect(adminLevelBorder(level)).toMatch(/var\(--(status|border)-/);
    }
  });
});
