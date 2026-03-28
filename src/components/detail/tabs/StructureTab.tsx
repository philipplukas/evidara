"use client";

import { BookOpen } from "lucide-react";
import type { LocalStructureItem } from "@/lib/types";

interface StructureTabProps {
  items: LocalStructureItem[];
  onFocus?: (id: string) => void;
}

export function StructureTab({ items, onFocus }: StructureTabProps) {
  return (
    <div className="p-5">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
        Local Structure
      </h4>
      <div className="space-y-0.5">
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => onFocus?.(item.id)}
            className={`flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer transition-all text-xs
              ${
                item.active
                  ? "bg-[#2563eb]/5 text-[#2563eb] font-semibold border-l-2 border-l-[#2563eb]"
                  : "text-foreground/70 hover:bg-muted/50 hover:text-foreground border-l-2 border-l-transparent"
              }`}
          >
            <BookOpen className="w-3 h-3 shrink-0" />
            <span className="truncate">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
