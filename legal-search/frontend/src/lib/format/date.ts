/**
 * Swiss-locale date formatting contract (Sprint 1 — TAR-244).
 *
 * A single source of truth for how dates and timestamps render across the
 * legal-search surface. Both surfaces (legal-search + admin control plane)
 * import an equivalent module so a given ISO string renders identically
 * in every view — result cards, detail metadata, admin lists, admin show
 * pages, and the mobile detail sheet.
 *
 * Format contract:
 * - Dates:      `DD.MM.YYYY`           (e.g. `03.04.2026`)
 * - Timestamps: `DD.MM.YYYY, HH:mm`    (e.g. `03.04.2026, 14:30`)
 *
 * Locale: `de-CH` (24-hour clock, leading zeros, dot separators).
 *
 * See also `platform-control/admin/src/lib/format/date.ts`.
 */

const SWISS_LOCALE = "de-CH";
// Pinning the timezone means a Swiss legal document always renders in
// Swiss wall-clock time, independent of where the server or user's
// device happens to be. Avoids `14:30 CEST` → `12:30 UTC` drift in SSR.
const SWISS_TIME_ZONE = "Europe/Zurich";

const dateFormatter = new Intl.DateTimeFormat(SWISS_LOCALE, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: SWISS_TIME_ZONE,
});

const dateTimeFormatter = new Intl.DateTimeFormat(SWISS_LOCALE, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: SWISS_TIME_ZONE,
});

function toDate(value: string | number | Date | null | undefined): Date | null {
  if (value == null || value === "") return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * Format an ISO-ish value as `DD.MM.YYYY`. Returns `""` for missing/invalid
 * inputs so callers can render directly without guard logic.
 */
export function formatSwissDate(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  return d ? dateFormatter.format(d) : "";
}

/**
 * Format an ISO-ish value as `DD.MM.YYYY, HH:mm`. Returns `""` for
 * missing/invalid inputs.
 */
export function formatSwissDateTime(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  return d ? dateTimeFormatter.format(d) : "";
}
