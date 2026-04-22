"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "evidara:saved-searches";
const MAX_SAVED_SEARCHES = 20;

export interface SavedSearch {
  id: string;
  name: string;
  query: string;
  filters: {
    jurisdictions: string[];
    languages: string[];
    sourceType: string | null;
    officialOnly: boolean;
  };
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Tiny pub/sub so every hook instance re-renders when storage changes
// ---------------------------------------------------------------------------

const listeners = new Set<() => void>();

function emitChange() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): SavedSearch[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry): entry is SavedSearch =>
        typeof entry === "object" &&
        entry !== null &&
        typeof entry.id === "string" &&
        typeof entry.name === "string" &&
        typeof entry.query === "string",
    );
  } catch {
    return [];
  }
}

function getServerSnapshot(): SavedSearch[] {
  return [];
}

// Keep a stable reference between snapshots when the underlying data hasn't changed.
let cachedJson = "";
let cachedResult: SavedSearch[] = [];

function getStableSnapshot(): SavedSearch[] {
  const items = getSnapshot();
  const json = JSON.stringify(items);
  if (json !== cachedJson) {
    cachedJson = json;
    cachedResult = items;
  }
  return cachedResult;
}

function persist(items: SavedSearch[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Ignore quota or privacy-mode failures.
  }
  emitChange();
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSavedSearches() {
  const savedSearches = useSyncExternalStore(subscribe, getStableSnapshot, getServerSnapshot);

  const saveSearch = useCallback(
    (entry: Omit<SavedSearch, "id" | "createdAt">) => {
      const next: SavedSearch[] = [
        {
          ...entry,
          id: crypto.randomUUID(),
          createdAt: new Date().toISOString(),
        },
        ...savedSearches,
      ].slice(0, MAX_SAVED_SEARCHES);

      persist(next);
    },
    [savedSearches],
  );

  const removeSearch = useCallback(
    (id: string) => {
      persist(savedSearches.filter((s) => s.id !== id));
    },
    [savedSearches],
  );

  return { savedSearches, saveSearch, removeSearch } as const;
}
