"use client";

import { Zap } from "lucide-react";
import type { SearchResultViewModel } from "@/lib/types";
import { getIcon } from "@/lib/icons";
import { Badge } from "../primitives";

interface ExactMatchStripProps {
  matches: SearchResultViewModel[];
  onSelect: (id: string) => void;
}

export function ExactMatchStrip({ matches, onSelect }: ExactMatchStripProps) {
  if (matches.length === 0) return null;

  return (
    <div className="mb-4 px-4 py-3 rounded-lg bg-brand/[0.03] border border-brand/10">
      <div className="flex items-center gap-2 mb-2">
        <Zap className="w-3.5 h-3.5 text-brand" />
        <span className="text-xs font-semibold text-brand">Exact match</span>
      </div>
      <div className="flex gap-2">
        {matches.map((match) => {
          const icon = match.badges[0]?.iconKey
            ? getIcon(match.badges[0].iconKey)
            : null;
          return (
            <button
              key={match.id}
              onClick={() => onSelect(match.id)}
              className="flex items-center gap-2 px-3 py-2 rounded-md bg-surface-panel border border-border
                hover:border-brand/30 hover:shadow-sm transition-all text-left"
            >
              {icon && <span className="text-sm">{icon}</span>}
              <div>
                <div className="text-sm font-medium text-foreground">
                  {match.title}
                </div>
                <div className="text-xs text-muted-foreground">
                  {match.subtitle}
                </div>
              </div>
              <Badge
                label={match.badges[0]?.label ?? ""}
                colorKey={match.badges[0]?.colorKey}
                className="ml-2"
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
