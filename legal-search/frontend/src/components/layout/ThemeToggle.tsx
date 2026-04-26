"use client";

import { Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useThemePreference } from "@/hooks/use-theme-preference";

/**
 * Theme toggle button — switches between light and dark mode.
 *
 * Reads initial preference from localStorage (`evidara:theme`), falling back
 * to `prefers-color-scheme`. Persists choice on toggle. The root layout's
 * inline script handles flash prevention so the first paint is always correct.
 */
export function ThemeToggle() {
  const t = useTranslations("theme");
  const { theme, mounted, toggle } = useThemePreference();

  if (!mounted) {
    return (
      <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg" aria-hidden />
    );
  }

  const label = theme === "dark" ? t("switchToLight") : t("switchToDark");

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className="inline-flex min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
