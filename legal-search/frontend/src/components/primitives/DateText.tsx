import type { HTMLAttributes } from "react";
import { formatSwissDate, formatSwissDateTime } from "@/lib/format/date";

interface DateTextProps extends Omit<HTMLAttributes<HTMLTimeElement>, "children"> {
  value: string | number | Date | null | undefined;
  /** Render `DD.MM.YYYY, HH:mm` instead of `DD.MM.YYYY`. */
  showTime?: boolean;
  /** Fallback string when the value is missing/invalid (defaults to `—`). */
  emptyText?: string;
}

/**
 * Swiss-locale date primitive. Use wherever the UI prints a date/timestamp
 * so every surface reads `DD.MM.YYYY` consistently. Applies
 * `font-variant-numeric: tabular-nums` so digits line up in columns.
 *
 * Pairs with `platform-control/admin/src/components/DateText.tsx` — both
 * primitives produce the exact same output for the same ISO input.
 */
export function DateText({
  value,
  showTime = false,
  emptyText = "—",
  className = "",
  ...rest
}: DateTextProps) {
  const formatted = showTime ? formatSwissDateTime(value) : formatSwissDate(value);
  const display = formatted || emptyText;
  const datetime = value instanceof Date ? value.toISOString() : value ? String(value) : undefined;
  return (
    <time dateTime={datetime} className={`tabular-nums ${className}`.trim()} {...rest}>
      {display}
    </time>
  );
}
