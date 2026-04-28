import type { CSSProperties, ReactNode } from "react";
import { BrandMark, type BrandMarkSize } from "./BrandMark";

export type BrandLockupTone = "light" | "dark";

interface BrandLockupProps {
  /**
   * Mark size. `compact` (32px) for dense workspace chrome,
   * `prominent` (42px) for the admin header. Default: `prominent`.
   */
  size?: BrandMarkSize;
  /**
   * Optional secondary label rendered under the wordmark
   * (e.g. "Control plane" on the admin surface). Workspace
   * renders only the wordmark today.
   */
  subLabel?: ReactNode;
  /**
   * Surrounding chrome tone. `light` (default) renders the wordmark
   * in `--brand-strong`; `dark` renders it via `currentColor` so the
   * parent's text color carries through (admin's gradient header
   * uses `--admin-on-brand`). The mark itself is tone-invariant.
   */
  tone?: BrandLockupTone;
  /** Override the wordmark text. Default: "Evidara". */
  wordmark?: string;
  className?: string;
  markClassName?: string;
  /** Hide the wordmark; render only the mark. */
  iconOnly?: boolean;
  style?: CSSProperties;
}

const WORDMARK_FONT_PX: Record<BrandMarkSize, number> = {
  compact: 18,
  prominent: 18,
};

const SUB_LABEL_FONT_PX: Record<BrandMarkSize, number> = {
  compact: 12,
  prominent: 13,
};

export function BrandLockup({
  size = "prominent",
  subLabel,
  tone = "light",
  wordmark = "Evidara",
  className,
  markClassName,
  iconOnly = false,
  style,
}: BrandLockupProps) {
  const wordmarkColor =
    tone === "dark" ? "currentColor" : "var(--brand-wordmark-color, var(--brand-strong))";
  const subLabelColor =
    tone === "dark"
      ? "var(--brand-sublabel-color, color-mix(in oklab, currentColor 78%, transparent))"
      : "var(--brand-sublabel-color, var(--foreground-muted))";

  const rootStyle: CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: size === "compact" ? 10 : 12,
    minWidth: 0,
    ...style,
  };

  return (
    <span data-evidara-brand-lockup={size} className={className} style={rootStyle}>
      <BrandMark size={size} className={markClassName} />
      {iconOnly ? null : (
        <span
          data-evidara-brand-lockup-text
          style={{ minWidth: 0, display: "flex", flexDirection: "column" }}
        >
          <span
            data-evidara-brand-wordmark
            style={{
              color: wordmarkColor,
              fontFamily: "var(--brand-wordmark-font, var(--font-admin-serif, Georgia, serif))",
              fontWeight: 600,
              fontSize: WORDMARK_FONT_PX[size],
              letterSpacing: "-0.01em",
              lineHeight: 1.15,
            }}
          >
            {wordmark}
          </span>
          {subLabel ? (
            <span
              data-evidara-brand-sublabel
              style={{
                color: subLabelColor,
                fontSize: SUB_LABEL_FONT_PX[size],
                fontWeight: 500,
                lineHeight: 1.25,
                marginTop: 2,
              }}
            >
              {subLabel}
            </span>
          ) : null}
        </span>
      )}
    </span>
  );
}
