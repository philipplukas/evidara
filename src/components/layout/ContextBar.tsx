"use client";

import { useState } from "react";
import { Shield } from "lucide-react";
import type { SearchContextViewModel } from "@/lib/types";
import { getIcon } from "@/lib/icons";

interface ContextBarProps {
  context: SearchContextViewModel;
}

export function ContextBar({ context }: ContextBarProps) {
  const [jurisdictions, setJurisdictions] = useState(context.jurisdictions);
  const [languages, setLanguages] = useState(context.languages);
  const [sourceTypes, setSourceTypes] = useState(context.sourceTypes);
  const [officialOnly, setOfficialOnly] = useState(false);

  const toggleChip = <T extends { key: string; active: boolean }>(
    items: T[],
    key: string,
    setter: (items: T[]) => void
  ) => {
    setter(
      items.map((item) =>
        item.key === key ? { ...item, active: !item.active } : item
      )
    );
  };

  return (
    <div className="border-b border-border bg-white px-6 py-2 flex items-center gap-6 text-sm">
      {/* Jurisdiction chips */}
      <ChipGroup
        items={jurisdictions}
        onToggle={(key) => toggleChip(jurisdictions, key, setJurisdictions)}
      />

      <div className="w-px h-5 bg-border" />

      {/* Language chips */}
      <ChipGroup
        items={languages}
        onToggle={(key) => toggleChip(languages, key, setLanguages)}
      />

      <div className="w-px h-5 bg-border" />

      {/* Source type tabs */}
      <TabGroup
        items={sourceTypes}
        onSelect={(key) =>
          setSourceTypes(
            sourceTypes.map((t) => ({ ...t, active: t.key === key }))
          )
        }
      />

      <div className="flex-1" />

      {/* Official sources toggle */}
      <button
        onClick={() => setOfficialOnly(!officialOnly)}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors
          ${
            officialOnly
              ? "text-[#2563eb] bg-[#2563eb]/5 border border-[#2563eb]/20"
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
                  ? "bg-[#1a2332] text-white shadow-sm"
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
                ? "text-[#2563eb] bg-[#2563eb]/5"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
