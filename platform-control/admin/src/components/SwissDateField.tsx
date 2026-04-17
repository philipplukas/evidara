"use client";

import { DateField, type DateFieldProps } from "react-admin";
import { SWISS_DATE_OPTIONS, SWISS_DATE_TIME_OPTIONS, SWISS_LOCALE } from "../lib/format/date";

/**
 * Thin wrapper around react-admin's `<DateField>` that pins the locale to
 * `de-CH` and forces `DD.MM.YYYY` / `DD.MM.YYYY, HH:mm` output so every
 * admin view renders timestamps consistently (Sprint 1 — TAR-244).
 *
 * Drop-in replacement — accepts the same props as `<DateField>`. Pass
 * `showTime` to switch between date-only and date+time format.
 *
 * Do NOT pass `locales` or `options` — those are owned by this wrapper.
 */
export function SwissDateField<
  RecordType extends Record<string, unknown> = Record<string, unknown>,
>(props: Omit<DateFieldProps<RecordType>, "locales" | "options">) {
  const options = props.showTime ? SWISS_DATE_TIME_OPTIONS : SWISS_DATE_OPTIONS;
  return <DateField<RecordType> {...props} locales={SWISS_LOCALE} options={options} />;
}
