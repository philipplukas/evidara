"use client";

import { Search, MapPin, Clock, User, SlidersHorizontal } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useWorkspace } from "@/lib/workspace-store";
import { searchResults } from "@/lib/mock-data";

interface AppHeaderProps {
  onOpenFilters?: () => void;
}

export function AppHeader({ onOpenFilters }: AppHeaderProps) {
  const { state, dispatch } = useWorkspace();
  const initialQuery =
    state.resultSet.source.type === "search" ? state.resultSet.source.query : "";
  const [query, setQuery] = useState(initialQuery);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    // In real app, this would call BFF. For now, re-use mock data.
    dispatch({ type: "SEARCH", query: query.trim(), results: searchResults });
  };

  return (
    <header className="border-b border-border bg-white">
      <div className="flex items-center gap-6 px-6 py-3">
        {/* Wordmark */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-[#1a2332] flex items-center justify-center">
            <span className="text-white font-bold text-sm">O</span>
          </div>
          <span className="text-lg font-semibold tracking-tight text-[#1a2332]">
            Omnilex
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
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-border bg-[#f8f9fa] text-sm
                focus:outline-none focus:ring-2 focus:ring-[#2563eb]/20 focus:border-[#2563eb]
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
          <button className="w-8 h-8 rounded-full bg-[#2563eb]/10 flex items-center justify-center
            hover:bg-[#2563eb]/20 transition-colors">
            <User className="w-4 h-4 text-[#2563eb]" />
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
            ? "text-[#2563eb] bg-[#2563eb]/5"
            : "text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
    >
      {icon}
      {label}
      {count != null && (
        <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-[#2563eb]/10 text-[10px] font-semibold text-[#2563eb] leading-none">
          {count}
        </span>
      )}
    </button>
  );
}
