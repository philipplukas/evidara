"use client";

import { ChevronRight } from "lucide-react";

interface BreadcrumbsProps {
  items: string[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <div className="flex items-center gap-1 text-[11px] text-muted-foreground/70 flex-wrap">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="w-2.5 h-2.5" />}
          <span className={i === items.length - 1 ? "font-medium text-foreground/60" : ""}>
            {item}
          </span>
        </span>
      ))}
    </div>
  );
}
