/**
 * Swiss-locale date formatting — admin control plane.
 *
 * Mirror of `legal-search/frontend/src/lib/format/date.ts`. Both modules
 * MUST produce identical output for the same ISO input so operators see
 * one consistent date vocabulary across both surfaces. (Sprint 1 — TAR-244.)
 *
 * Format contract:
 * - Dates:      `DD.MM.YYYY`           (e.g. `03.04.2026`)
 * - Timestamps: `DD.MM.YYYY, HH:mm`    (e.g. `03.04.2026, 14:30`)
 *
 * Locale: `de-CH` (24-hour clock, leading zeros, dot separators).
 *
 * A cross-surface parity test lives at
 * `legal-search/frontend/src/__tests__/date-format.cross-surface.test.ts`.
 */

export const SWISS_LOCALE = "de-CH";
// Pinning the timezone keeps wall-clock time stable whether the admin is
// viewed from a Swiss operator's laptop, a UTC-hosted dev container, or
// the CI runner. See `legal-search/frontend/src/lib/format/date.ts`.
export const SWISS_TIME_ZONE = "Europe/Zurich";

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

export function formatSwissDate(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  return d ? dateFormatter.format(d) : "";
}

export function formatSwissDateTime(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  return d ? dateTimeFormatter.format(d) : "";
}

/**
 * Intl options used by the `<SwissDateField>` wrapper. Exported so raw
 * `<DateField>` usages that need the same format without the wrapper can
 * opt in explicitly (`<DateField locales={SWISS_LOCALE} options={SWISS_DATE_OPTIONS} />`).
 */
export const SWISS_DATE_OPTIONS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  timeZone: SWISS_TIME_ZONE,
};

export const SWISS_DATE_TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: SWISS_TIME_ZONE,
};
