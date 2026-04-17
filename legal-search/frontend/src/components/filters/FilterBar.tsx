"use client";

import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { FilterViewModel } from "@/lib/types";

interface FilterBarProps {
  filters: FilterViewModel[];
}

export function FilterBar({ filters }: FilterBarProps) {
  const { state: constraints, dispatch } = useSearchConstraints();
  const t = useTranslations("filter");
  const activeCount = constraints.refinements.length;

  const activeRefinements = constraints.refinements.map((refinement) => {
    const filter = filters.find((f) => f.key === refinement.field);
    const labels = refinement.values
      .map((v) => filter?.options.find((o) => o.value === v)?.label ?? v)
      .join(", ");
    return {
      field: refinement.field,
      filterLabel: filter?.label ?? refinement.field,
      valueLabels: labels,
    };
  });

  if (activeCount === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 sm:px-5">
      <span className="shrink-0 text-tiny font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {activeCount} {activeCount === 1 ? "active filter" : "active filters"}
      </span>
      {activeRefinements.map((item) => (
        <span
          key={item.field}
          className="inline-flex items-center gap-1 rounded-full border border-accent-core/15 bg-interactive-accent-subtle px-2 py-0.5 text-xs font-medium text-accent-core"
        >
          <span className="max-w-[12rem] truncate">
            {item.filterLabel}: {item.valueLabels}
          </span>
          <button
            type="button"
            onClick={() => dispatch({ type: "CLEAR_REFINEMENT", field: item.field })}
            className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-accent-core/10"
            aria-label={`Remove ${item.filterLabel} filter`}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <button
        type="button"
        onClick={() => dispatch({ type: "CLEAR_ALL_REFINEMENTS" })}
        className="shrink-0 rounded-sm px-1.5 py-0.5 text-xs font-medium text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline"
      >
        {t("clearAll")}
      </button>
    </div>
  );
}
