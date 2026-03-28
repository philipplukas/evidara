"use client";

import { Search, MapPin, Clock, User, SlidersHorizontal } from "lucide-react";
import { useState, useEffect, type FormEvent } from "react";
import { useWorkspace } from "@/lib/workspace-store";
import { searchResults } from "@/lib/mock-data";

interface AppHeaderProps {
  onOpenFilters?: () => void;
}

export function AppHeader({ onOpenFilters }: AppHeaderProps) {
  const { state, dispatch } = useWorkspace();
  const storeQuery =
    state.resultSet.source.type === "search" ? state.resultSet.source.query : "";
  const [query, setQuery] = useState(storeQuery);

  // Keep the input in sync when a SEARCH is dispatched from elsewhere
  useEffect(() => {
    setQuery(storeQuery);
  }, [storeQuery]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    dispatch({ type: "SEARCH", query: query.trim(), results: searchResults });
  };

  return (
    <header className="border-b border-border bg-surface-panel">
      <div className="flex items-center gap-6 px-6 py-3">
        {/* Wordmark */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-brand-strong flex items-center justify-center">
            <span className="text-white font-bold text-sm">E</span>
          </div>
          <span className="text-lg font-semibold tracking-tight text-brand-strong">
            Evidara
          </span>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSubmit} className="flex-1 max-w-2xl">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
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
          <button className="w-8 h-8 rounded-full bg-interactive-accent-muted flex items-center justify-center
            hover:bg-brand/20 transition-colors">
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
