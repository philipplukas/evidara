"use client";

import type { MetadataRow } from "@/lib/types";
import { getIcon } from "@/lib/icons";

interface MetadataSectionProps {
  rows: MetadataRow[];
}

export function MetadataSection({ rows }: MetadataSectionProps) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Metadata
      </h4>
      <div className="space-y-1.5">
        {rows.map((row, i) => {
          const icon = getIcon(row.iconKey);
          return (
            <div key={i} className="flex items-baseline gap-2 text-xs">
              <span className="text-muted-foreground w-28 shrink-0 font-medium">
                {row.label}
              </span>
              <span className="text-foreground/80 flex items-center gap-1">
                {icon && <span className="text-sm">{icon}</span>}
                {row.value}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
