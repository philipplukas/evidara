"use client";

import { Zap } from "lucide-react";
import type { SearchResultViewModel } from "@/lib/types";
import { getIcon } from "@/lib/icons";

interface ExactMatchStripProps {
  matches: SearchResultViewModel[];
  onSelect: (id: string) => void;
}

export function ExactMatchStrip({ matches, onSelect }: ExactMatchStripProps) {
  if (matches.length === 0) return null;

  return (
    <div className="mb-4 px-4 py-3 rounded-lg bg-[#2563eb]/[0.03] border border-[#2563eb]/10">
      <div className="flex items-center gap-2 mb-2">
        <Zap className="w-3.5 h-3.5 text-[#2563eb]" />
        <span className="text-xs font-semibold text-[#2563eb]">Exact match</span>
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
              className="flex items-center gap-2 px-3 py-2 rounded-md bg-white border border-border
                hover:border-[#2563eb]/30 hover:shadow-sm transition-all text-left"
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
              <span
                className="px-1.5 py-0.5 rounded text-[10px] font-medium ml-2"
                style={{
                  backgroundColor: getBadgeColor(match.badges[0]?.colorKey).bg,
                  color: getBadgeColor(match.badges[0]?.colorKey).text,
                }}
              >
                {match.badges[0]?.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Badge color system ───

const badgeColors: Record<string, { bg: string; text: string }> = {
  law: { bg: "#dbeafe", text: "#1e40af" },
  decision: { bg: "#fce7f3", text: "#9d174d" },
  rechtssatz: { bg: "#e0e7ff", text: "#3730a3" },
  commentary: { bg: "#d1fae5", text: "#065f46" },
};

export function getBadgeColor(colorKey?: string): { bg: string; text: string } {
  return (
    badgeColors[colorKey || ""] || { bg: "#f3f4f6", text: "#374151" }
  );
}
