"use client";

import { Check, Link } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useRef, useState } from "react";
import { AnalyticsEvent, track } from "@/lib/analytics";

interface ShareButtonProps {
  /** URL to copy. Defaults to `window.location.href`. */
  url?: string;
  /** Visual size variant. */
  size?: "default" | "sm";
  /** Extra classes forwarded to the outer button. */
  className?: string;
  /** Accessible label override. */
  label?: string;
}

/** Resolves `url` (which may be relative, e.g. a result deep link) to an absolute URL. */
function resolveShareTarget(url?: string): string {
  if (!url) return window.location.href;
  return new URL(url, window.location.href).toString();
}

/**
 * Copies the current page URL (or a custom URL) to the clipboard.
 * Shows a Link icon that transitions to a Check icon for 2 seconds
 * with a brief "Link copied" tooltip.
 */
export function ShareButton({
  url,
  size = "default",
  className = "",
  label,
}: ShareButtonProps) {
  const t = useTranslations("share");
  const resolvedLabel = label ?? t("copyLink");
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      const target = resolveShareTarget(url);
      void navigator.clipboard.writeText(target);
      track(AnalyticsEvent.SHARE_LINK_COPIED, { url: target, context: "share_button" });

      setCopied(true);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => setCopied(false), 2000);
    },
    [url],
  );

  const sizeClasses =
    size === "sm"
      ? "h-7 w-7 rounded-md"
      : "min-h-11 sm:min-h-0 px-3 py-2 sm:px-2 sm:py-1 rounded gap-1";

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={copied ? t("linkCopied") : resolvedLabel}
      aria-label={copied ? t("linkCopied") : resolvedLabel}
      className={`flex shrink-0 items-center justify-center text-micro font-medium transition-all
        ${
          copied
            ? "text-success bg-success/10"
            : "text-muted-foreground hover:text-accent-core hover:bg-interactive-accent-subtle"
        } ${sizeClasses} ${className}`}
    >
      {copied ? <Check className="h-3 w-3" /> : <Link className="h-3 w-3" />}
    </button>
  );
}
