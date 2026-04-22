"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

// ─── Types ───

export type ResultsPerPage = 10 | 25 | 50;
export type SortOrder = "relevance" | "date-desc" | "date-asc";
export type Theme = "light" | "dark" | "system";
export type PreferredLanguage = "de" | "fr" | "it";

export interface Preferences {
  resultsPerPage: ResultsPerPage;
  sortOrder: SortOrder;
  theme: Theme;
  language: PreferredLanguage;
}

// ─── Defaults ───

const STORAGE_KEY = "evidara:preferences";

export const DEFAULT_PREFERENCES: Preferences = {
  resultsPerPage: 25,
  sortOrder: "relevance",
  theme: "system",
  language: "de",
};

// ─── Helpers ───

function readStorage(): Preferences {
  if (typeof window === "undefined") {
    return DEFAULT_PREFERENCES;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return DEFAULT_PREFERENCES;
    }

    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
      return DEFAULT_PREFERENCES;
    }

    const obj = parsed as Record<string, unknown>;

    return {
      resultsPerPage: ([10, 25, 50] as const).includes(obj.resultsPerPage as ResultsPerPage)
        ? (obj.resultsPerPage as ResultsPerPage)
        : DEFAULT_PREFERENCES.resultsPerPage,
      sortOrder: (["relevance", "date-desc", "date-asc"] as const).includes(
        obj.sortOrder as SortOrder,
      )
        ? (obj.sortOrder as SortOrder)
        : DEFAULT_PREFERENCES.sortOrder,
      theme: (["light", "dark", "system"] as const).includes(obj.theme as Theme)
        ? (obj.theme as Theme)
        : DEFAULT_PREFERENCES.theme,
      language: (["de", "fr", "it"] as const).includes(obj.language as PreferredLanguage)
        ? (obj.language as PreferredLanguage)
        : DEFAULT_PREFERENCES.language,
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function writeStorage(prefs: Preferences): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore quota or privacy-mode failures.
  }
}

// ─── Hook ───

export function usePreferences() {
  const [preferences, setPreferencesState] = useState<Preferences>(DEFAULT_PREFERENCES);

  // Hydrate from localStorage on mount (SSR-safe: starts with defaults).
  useEffect(() => {
    setPreferencesState(readStorage());
  }, []);

  const setPreferences = useCallback((next: Partial<Preferences>) => {
    setPreferencesState((prev) => {
      const merged = { ...prev, ...next };
      writeStorage(merged);
      return merged;
    });
  }, []);

  return useMemo(() => ({ preferences, setPreferences }) as const, [preferences, setPreferences]);
}
