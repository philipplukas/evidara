"use client";

import { useTranslations } from "next-intl";

/**
 * Link from the search header to the public source repository.
 *
 * The mark is an inline SVG, not a lucide component, because lucide-react v1
 * removed its brand icons — `lucide-react` exports 5,816 symbols and none of
 * them is `Github`. Importing one would typecheck as `undefined` and render
 * nothing, which is the silent-empty failure mode this repo keeps filing bugs
 * about, so the geometry is carried here instead.
 *
 * `fill="currentColor"` on purpose: the mark inherits the same
 * `text-muted-foreground` → `hover:text-foreground` token transition as the
 * sibling utility-strip controls, so it themes in dark mode without a second
 * asset and without a hardcoded colour (AGENTS.md design-token rule).
 */

/** The public repository this deployment is built from. */
export const REPOSITORY_URL = "https://github.com/philipplukas/evidara";

/** Official GitHub mark, authored on a 16x16 grid. */
const GITHUB_MARK =
  "M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0016 8c0-4.42-3.58-8-8-8z";

export function RepositoryLink({ className = "" }: { className?: string }) {
  const t = useTranslations();
  const label = t("header.repository");

  return (
    <a
      href={REPOSITORY_URL}
      target="_blank"
      // `noopener` is the security half and `noreferrer` the privacy half;
      // both are required on a `target="_blank"` to an external origin.
      rel="noopener noreferrer"
      title={label}
      className={`inline-flex items-center rounded-md px-2.5 py-1 text-xs font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground ${className}`}
    >
      <svg
        width={16}
        height={16}
        viewBox="0 0 16 16"
        fill="currentColor"
        aria-hidden="true"
        focusable="false"
      >
        <path d={GITHUB_MARK} />
      </svg>
      {/*
        Visually-hidden text, not `aria-label`, and Biome's `useAnchorContent`
        is right to insist: the only child is an `aria-hidden` SVG, so the link
        has no accessible name in the tree at all without this. Real text also
        survives translation and reads correctly when CSS fails to load.
      */}
      <span className="sr-only">{label}</span>
    </a>
  );
}
