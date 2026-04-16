import { describe, expect, it } from "vitest";
import { formatSwissDate, formatSwissDateTime } from "../format/date";

/**
 * Sprint 1 (TAR-244) — Swiss date contract test (admin side).
 *
 * Mirror: `legal-search/frontend/src/__tests__/date-format.cross-surface.test.ts`.
 * Keep fixtures in sync between the two files so the format contract
 * (`DD.MM.YYYY` / `DD.MM.YYYY, HH:mm`, `de-CH`, 24-hour clock) cannot
 * drift between surfaces.
 */

describe("Swiss date formatter — admin format contract", () => {
  it("formats date-only as DD.MM.YYYY", () => {
    expect(formatSwissDate("2026-04-03T14:30:00+02:00")).toBe("03.04.2026");
    expect(formatSwissDate("2025-12-31T23:59:00+01:00")).toBe("31.12.2025");
    expect(formatSwissDate("2024-01-01T00:00:00+01:00")).toBe("01.01.2024");
  });

  it("formats timestamps as DD.MM.YYYY, HH:mm", () => {
    expect(formatSwissDateTime("2026-04-03T14:30:00+02:00")).toBe("03.04.2026, 14:30");
    expect(formatSwissDateTime("2026-04-03T08:05:00+02:00")).toBe("03.04.2026, 08:05");
  });

  it("uses the 24-hour clock, never AM/PM", () => {
    expect(formatSwissDateTime("2026-04-03T13:05:00+02:00")).not.toMatch(/AM|PM/i);
    expect(formatSwissDateTime(new Date(Date.UTC(2026, 3, 3, 22, 0)))).not.toMatch(/AM|PM/i);
  });

  it.each([
    null,
    undefined,
    "",
    "not-a-date",
    Number.NaN,
  ])("returns empty string for invalid input (%s)", (value) => {
    expect(formatSwissDate(value as never)).toBe("");
    expect(formatSwissDateTime(value as never)).toBe("");
  });

  it("accepts Date instances as well as ISO strings", () => {
    const d = new Date("2026-04-03T14:30:00Z");
    expect(formatSwissDate(d)).toBe(formatSwissDate(d.toISOString()));
    expect(formatSwissDateTime(d)).toBe(formatSwissDateTime(d.toISOString()));
  });
});
