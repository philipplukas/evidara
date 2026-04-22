"use client";

import { ChevronRight } from "lucide-react";

interface BreadcrumbsProps {
  items: string[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-1 text-micro text-muted-foreground/70 flex-wrap list-none m-0 p-0">
        {items.map((item, i) => (
          <li key={i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="w-2.5 h-2.5" aria-hidden="true" />}
            <span
              className={i === items.length - 1 ? "font-medium text-foreground/60" : ""}
              {...(i === items.length - 1 ? { "aria-current": "page" as const } : {})}
            >
              {item}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
