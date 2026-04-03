"use client";

import { Clock, MapPin, Search, SlidersHorizontal, User } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { type FormEvent, useEffect, useState } from "react";
import { searchMockResults } from "@/lib/mock-data";
import { useWorkspace } from "@/lib/workspace-store";

interface AppHeaderProps {
  onOpenFilters?: () => void;
}

export function AppHeader({ onOpenFilters }: AppHeaderProps) {
  const { state, dispatch } = useWorkspace();
  const [urlQuery, setUrlQuery] = useQueryState("q", parseAsString.withDefault(""));
  const storeQuery = state.resultSet.source.type === "search" ? state.resultSet.source.query : "";

  // Local input state — syncs with store query but allows free typing
  const [inputValue, setInputValue] = useState(storeQuery);

  // Sync input when store query changes (e.g., from URL navigation)
  useEffect(() => {
    setInputValue(storeQuery);
  }, [storeQuery]);

  // On mount or when the URL ?q= param changes (e.g. browser back/forward),
  // resync the store search state if needed.
  useEffect(() => {
    if (urlQuery && urlQuery !== storeQuery) {
      const results = searchMockResults(urlQuery);
      dispatch({ type: "SEARCH", query: urlQuery, results });
    }
  }, [urlQuery, storeQuery, dispatch]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed) return;

    const results = searchMockResults(trimmed);
    dispatch({ type: "SEARCH", query: trimmed, results });
    setUrlQuery(trimmed);
  };

  return (
    <header className="border-b border-border bg-surface-panel">
      <div className="flex items-center gap-6 px-6 py-3">
        {/* Wordmark */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-brand-strong flex items-center justify-center">
            <span className="text-white font-bold text-sm">E</span>
          </div>
          <span className="text-lg font-semibold tracking-tight text-brand-strong">Evidara</span>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSubmit} className="flex-1 max-w-2xl">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Search article, case, commentary, citation…"
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-border bg-surface-input text-sm
                focus:outline-none focus:ring-2 focus:ring-focus-ring focus:border-brand
                placeholder:text-muted-foreground/60 transition-all"
            />
          </div>
        </form>

        {/* Navigation */}
        <nav className="flex items-center gap-1 shrink-0">
          {onOpenFilters && (
            <button
              type="button"
              onClick={onOpenFilters}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium
                text-muted-foreground hover:text-foreground hover:bg-muted transition-colors lg:hidden"
            >
              <SlidersHorizontal className="w-4 h-4" />
              Filters
            </button>
          )}
          <NavLink
            icon={<Clock className="w-4 h-4" />}
            label="Trail"
            count={state.trail.length > 0 ? state.trail.length : undefined}
          />
          <NavLink
            icon={<MapPin className="w-4 h-4" />}
            label="Pinned"
            count={state.pinned.length > 0 ? state.pinned.length : undefined}
          />
        </nav>

        {/* User */}
        <div className="flex items-center gap-2 shrink-0 pl-2 border-l border-border">
          <button
            type="button"
            aria-label="Open user menu"
            className="w-8 h-8 rounded-full bg-interactive-accent-muted flex items-center justify-center
            hover:bg-brand/20 transition-colors"
          >
            <User className="w-4 h-4 text-brand" />
          </button>
        </div>
      </div>
    </header>
  );
}

function NavLink({
  icon,
  label,
  active,
  count,
}: {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  count?: number;
}) {
  return (
    <button
      type="button"
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors
        ${
          active
            ? "text-brand bg-interactive-accent-subtle"
            : "text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
    >
      {icon}
      {label}
      {count != null && (
        <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-interactive-accent-muted text-tiny font-semibold text-brand leading-none">
          {count}
        </span>
      )}
    </button>
  );
}
