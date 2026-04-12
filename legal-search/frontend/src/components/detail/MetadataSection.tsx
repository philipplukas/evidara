"use client";

import { getIcon } from "@/lib/icons";
import type { MetadataRow } from "@/lib/types";
import { SectionLabel } from "../primitives";

interface MetadataSectionProps {
  rows: MetadataRow[];
}

export function MetadataSection({ rows }: MetadataSectionProps) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      <SectionLabel>Metadata</SectionLabel>
      <div className="space-y-1.5">
        {rows.map((row, i) => {
          const icon = getIcon(row.iconKey);
          const hasValue = row.value.trim().length > 0;
          return (
            <div key={i} className="flex items-baseline gap-2 text-xs">
              <span className="text-muted-foreground w-28 shrink-0 font-medium">{row.label}</span>
              <span
                className={
                  hasValue
                    ? "text-foreground/80 flex items-center gap-1"
                    : "text-muted-foreground/70 italic flex items-center gap-1"
                }
              >
                {icon && <span className="text-sm">{icon}</span>}
                {hasValue ? row.value : "Not available"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
