"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "evidara:theme";

export type Theme = "light" | "dark";

function getSystemTheme(): Theme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function getStoredTheme(): Theme | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Ignore storage errors (privacy mode, quota).
  }
  return null;
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export interface ThemePreference {
  theme: Theme;
  mounted: boolean;
  setTheme: (next: Theme) => void;
  toggle: () => void;
}

export function useThemePreference(): ThemePreference {
  const [theme, setThemeState] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const resolved = getStoredTheme() ?? getSystemTheme();
    setThemeState(resolved);
    applyTheme(resolved);
    setMounted(true);
  }, []);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      if (getStoredTheme() !== null) return;
      const next: Theme = e.matches ? "dark" : "light";
      setThemeState(next);
      applyTheme(next);
    };
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  const setTheme = (next: Theme) => {
    setThemeState(next);
    applyTheme(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Ignore storage errors.
    }
  };

  const toggle = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  return { theme, mounted, setTheme, toggle };
}
