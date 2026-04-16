import { describe, expect, it } from "vitest";
import { formatSwissDate, formatSwissDateTime } from "../lib/format/date";

/**
 * Sprint 1 (TAR-244) — Swiss date contract test (legal-search side).
 *
 * Mirror: `platform-control/admin/src/lib/__tests__/date.swiss.test.ts`.
 * Both files exercise the same fixtures against their respective
 * formatter modules. If both pass, the two surfaces format dates
 * identically; operators moving between surfaces never see drifting
 * `3/12/2025, 8:00:00 AM` vs `12.03.2025, 08:00` formats again.
 *
 * The contract is documented in `docs/design-system.md` §"Date
 * formatting contract". Do not weaken a fixture without updating that
 * section AND the admin-side mirror test.
 */

describe("Swiss date formatter — format contract", () => {
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
    // Use a fixed Date so the assertion is independent of the host timezone.
    // 2026-04-03 13:05:00 UTC stays afternoon in every sensible TZ.
    expect(formatSwissDateTime("2026-04-03T13:05:00+02:00")).not.toMatch(/AM|PM/i);
    // Ask the formatter with an explicit Date — de-CH never emits AM/PM.
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
