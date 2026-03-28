"use client";

import { Shield } from "lucide-react";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { SearchContextViewModel } from "@/lib/types";
import { getIcon } from "@/lib/icons";

interface ContextBarProps {
  context: SearchContextViewModel;
}

/**
 * Top-level, high-signal search constraints.
 * Reads/writes through SearchConstraintsProvider dispatch actions.
 */
export function ContextBar({ context }: ContextBarProps) {
  const { state: constraints, dispatch } = useSearchConstraints();

  return (
    <div className="border-b border-border bg-surface-panel px-6 py-2 flex items-center gap-6 text-sm">
      {/* Jurisdiction chips */}
      <ChipGroup
        items={context.jurisdictions.map((j) => ({
          ...j,
          active: constraints.context.jurisdictions.includes(j.key),
        }))}
        onToggle={(key) =>
          dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: key })
        }
      />

      <div className="w-px h-5 bg-border" />

      {/* Language chips */}
      <ChipGroup
        items={context.languages.map((l) => ({
          ...l,
          active: constraints.context.languages.includes(l.key),
        }))}
        onToggle={(key) =>
          dispatch({ type: "TOGGLE_LANGUAGE", language: key })
        }
      />

      <div className="w-px h-5 bg-border" />

      {/* Source type tabs */}
      <TabGroup
        items={context.sourceTypes.map((t) => ({
          ...t,
          active: constraints.context.sourceType === t.key || (constraints.context.sourceType === null && t.key === "all"),
        }))}
        onSelect={(key) =>
          dispatch({
            type: "SET_SOURCE_TYPE",
            sourceType: key === "all" ? null : key,
          })
        }
      />

      <div className="flex-1" />

      {/* Official sources toggle */}
      <button
        onClick={() =>
          dispatch({
            type: "SET_OFFICIAL_ONLY",
            value: !constraints.context.officialOnly,
          })
        }
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors
          ${
            constraints.context.officialOnly
              ? "text-brand bg-interactive-accent-subtle border border-brand/20"
              : "text-muted-foreground hover:text-foreground border border-transparent"
          }`}
      >
        <Shield className="w-3.5 h-3.5" />
        Official sources only
      </button>
    </div>
  );
}

function ChipGroup({
  items,
  onToggle,
}: {
  items: { key: string; label: string; active: boolean; iconKey?: string }[];
  onToggle: (key: string) => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {items.map((item) => {
        const icon = getIcon(item.iconKey);
        return (
          <button
            key={item.key}
            onClick={() => onToggle(item.key)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all
              ${
                item.active
                  ? "bg-brand-strong text-white shadow-sm"
                  : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
              }`}
          >
            {icon && <span className="text-sm leading-none">{icon}</span>}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

function TabGroup({
  items,
  onSelect,
}: {
  items: { key: string; label: string; active: boolean }[];
  onSelect: (key: string) => void;
}) {
  return (
    <div className="flex items-center gap-0.5">
      {items.map((item) => (
        <button
          key={item.key}
          onClick={() => onSelect(item.key)}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-all
            ${
              item.active
                ? "text-brand bg-interactive-accent-subtle"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
