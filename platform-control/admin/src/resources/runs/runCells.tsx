/**
 * The small rendering primitives every run-detail section shares.
 *
 * Extracted from `RunDetailSectionsV2.tsx` so that adding a section does not mean
 * editing the file every other section also lives in. See the module comment in
 * `runColumns.tsx` for why that mattered.
 */
"use client";

import { formatSwissDateTime } from "../../lib/format/date";
import type { PillLevel } from "../../ui/primitives";

// Re-exported so the run sections keep importing these from here. They live in
// `ui/primitives` now because `resources/sources` needs them too.
export { CodeBlock, formatJson } from "../../ui/primitives";

export const formatDateTime = (value: string | null | undefined): string =>
  formatSwissDateTime(value) || "—";

export const renderInlineValue = (value: string | number | null | undefined) =>
  value ?? <span className="text-[var(--foreground-faint)]">—</span>;

export function rowFailureLevel(isFailed: boolean): PillLevel {
  return isFailed ? "critical" : "neutral";
}

/**
 * Render `label` as an external link when `href` is non-null, and as the same
 * plain text when it is not.
 *
 * The fallback is the point, not a nicety: the link targets are tailnet-only and
 * some deployments configure none of them, so the unconfigured case must degrade
 * to exactly what this column showed before deep links existed. `runDeepLinks`
 * returns `null` for every unconfigured or unparseable input precisely so this
 * decision is made in one place.
 */
export function ExternalValueLink({ href, label }: { href: string | null; label: string }) {
  if (!href) {
    return <span className="font-mono text-[12px]">{label}</span>;
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-mono text-[12px] text-[var(--brand)] underline-offset-2 hover:underline"
    >
      {label}
    </a>
  );
}
