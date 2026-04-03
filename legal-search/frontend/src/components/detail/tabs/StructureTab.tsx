"use client";

import { BookOpen } from "lucide-react";
import type { KeyboardEvent } from "react";
import type { LocalStructureItem } from "@/lib/types";
import { SectionLabel } from "../../primitives";

interface StructureTabProps {
  items: LocalStructureItem[];
  onFocus?: (id: string) => void;
}

export function StructureTab({ items, onFocus }: StructureTabProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, id: string) => {
    if (!onFocus) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onFocus(id);
    }
  };

  return (
    <div className="p-5">
      <SectionLabel className="mb-3">Local Structure</SectionLabel>
      <div className="space-y-0.5">
        {items.map((item) => (
          <button
            type="button"
            key={item.id}
            onClick={() => onFocus?.(item.id)}
            onKeyDown={(event) => handleKeyDown(event, item.id)}
            className={`flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer transition-all text-xs
              ${
                item.active
                  ? "bg-interactive-accent-subtle text-brand font-semibold border-l-2 border-l-brand"
                  : "text-foreground/70 hover:bg-muted/50 hover:text-foreground border-l-2 border-l-transparent"
              }`}
          >
            <BookOpen className="w-3 h-3 shrink-0" />
            <span className="truncate">{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
