import type { ReactNode } from "react";
import { getFlagSrc, getIcon, getIconComponent, isFlagIcon } from "@/lib/icons";

interface MetadataIconProps {
  /** A key from the icon registry (see `@/lib/icons`), as emitted by the BFF. */
  iconKey?: string;
  /** Colour/spacing classes. Sizing comes from `size`, not from a text-* class. */
  className?: string;
  /** Edge length in px. Applies to all three render modes so a row of mixed
   *  icons (flag + lucide) lines up. */
  size?: number;
  /** Rendered when `iconKey` is absent or unknown to the registry. */
  fallback?: ReactNode;
  /** Alt text for the flag `<img>`. Empty by default: these icons decorate a
   *  label that already carries the meaning. */
  alt?: string;
}

/**
 * The one place the icon registry's three render modes are resolved (#694).
 *
 * Before this existed, six components each inlined the same
 * `isFlagIcon ? <img/> : <span>{getIcon()}</span>` ternary, which is how a
 * lucide `<Globe>` and a 🌐 emoji ended up a few pixels apart in ResultCard.
 * Document-meta keys now resolve to monochrome lucide components that inherit
 * `currentColor`, so they take a design token like every other icon in the
 * product. Flags and generated subdivision glyphs stay as-is — a jurisdiction
 * mark has no stroke-icon equivalent.
 */
export function MetadataIcon({
  iconKey,
  className,
  size = 14,
  fallback = null,
  alt = "",
}: MetadataIconProps) {
  if (!iconKey) return <>{fallback}</>;

  const Icon = getIconComponent(iconKey);
  if (Icon) {
    return (
      <Icon
        aria-hidden="true"
        width={size}
        height={size}
        className={`inline-block shrink-0${className ? ` ${className}` : ""}`}
      />
    );
  }

  if (isFlagIcon(iconKey)) {
    // Plain <img>, as at all six callsites this replaces: flags are static
    // SVGs already in public/flags, so next/image would add an optimizer
    // round-trip for no gain.
    return (
      <img
        src={getFlagSrc(iconKey)!}
        alt={alt}
        width={size}
        height={size}
        className={`inline-block shrink-0${className ? ` ${className}` : ""}`}
      />
    );
  }

  const text = getIcon(iconKey);
  if (!text) return <>{fallback}</>;

  return (
    <span
      aria-hidden="true"
      style={{ fontSize: `${size}px` }}
      className={`inline-block shrink-0 leading-none${className ? ` ${className}` : ""}`}
    >
      {text}
    </span>
  );
}
