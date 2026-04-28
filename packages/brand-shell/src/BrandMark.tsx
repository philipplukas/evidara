import type { CSSProperties } from "react";

export type BrandMarkSize = "compact" | "prominent";

const SIZE_PX: Record<BrandMarkSize, number> = {
  compact: 32,
  prominent: 42,
};

const RADIUS_PX: Record<BrandMarkSize, number> = {
  compact: 12,
  prominent: 16,
};

const FONT_PX: Record<BrandMarkSize, number> = {
  compact: 14,
  prominent: 18,
};

interface BrandMarkProps {
  size?: BrandMarkSize;
  className?: string;
  style?: CSSProperties;
}

export function BrandMark({ size = "prominent", className, style }: BrandMarkProps) {
  const px = SIZE_PX[size];

  const merged: CSSProperties = {
    width: px,
    height: px,
    borderRadius: RADIUS_PX[size],
    fontSize: FONT_PX[size],
    fontWeight: 700,
    lineHeight: 1,
    color: "#ffffff",
    background: "linear-gradient(135deg, var(--brand), var(--brand-hover))",
    boxShadow: "0 1px 2px rgb(15 76 129 / 18%)",
    fontFamily: "var(--brand-mark-font, var(--font-admin-serif, Georgia, serif))",
    display: "grid",
    placeItems: "center",
    flexShrink: 0,
    ...style,
  };

  return (
    <span aria-hidden className={className} data-evidara-brand-mark={size} style={merged}>
      E
    </span>
  );
}
