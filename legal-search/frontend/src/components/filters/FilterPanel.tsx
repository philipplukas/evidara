"use client";

import { ChevronDown, ChevronRight, Search, SlidersHorizontal } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { getFlagAlt, getFlagSrc, getIcon, isFlagIcon } from "@/lib/icons";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { FilterViewModel } from "@/lib/types";
import { SectionLabel } from "../primitives";
import { FilterBar } from "./FilterBar";

interface FilterPanelProps {
  filters: FilterViewModel[];
}

export function FilterPanel({ filters }: FilterPanelProps) {
  const { dispatch } = useSearchConstraints();
  const t = useTranslations();

  if (filters.length === 0) {
    return (
      <div className="px-4 py-4">
        <div className="rounded-2xl border border-dashed border-border/70 bg-surface-shell/45 px-4 py-5 text-center shadow-[--shadow-inset-surface]">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-interactive-accent-subtle text-accent-core">
            <SlidersHorizontal className="h-4 w-4" />
          </div>
          <SectionLabel className="mb-1">{t("filter.filtersTitle")}</SectionLabel>
          <p className="text-sm font-medium text-foreground">{t("filter.empty.title")}</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {t("filter.empty.description")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2 py-3">
      <FilterBar filters={filters} />
      <div className="px-4 pb-2">
        <div className="flex items-end justify-between gap-3 rounded-2xl border border-border/60 bg-surface-shell/45 px-3.5 py-3 shadow-[--shadow-inset-surface]">
          <SectionLabel>{t("filter.filtersTitle")}</SectionLabel>
          <div className="flex items-center gap-2 text-xs">
            <button
              type="button"
              onClick={() => dispatch({ type: "RESET_ALL" })}
              className="inline-flex items-center rounded-full border border-border/70 bg-surface-panel px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              {t("filter.resetAll")}
            </button>
          </div>
        </div>
      </div>
      {filters.map((filter) => (
        <FilterGroup key={filter.key} filter={filter} />
      ))}
    </div>
  );
}

function FilterGroup({ filter }: { filter: FilterViewModel }) {
  const { state: constraints, dispatch } = useSearchConstraints();
  const t = useTranslations();
  const [expanded, setExpanded] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  const refinement = constraints.refinements.find((r) => r.field === filter.key);
  const selected = refinement?.values ?? filter.selected;
  const selectedCount = selected.length;

  const toggle = (value: string) => {
    const next = selected.includes(value)
      ? selected.filter((v) => v !== value)
      : [...selected, value];

    if (next.length === 0) {
      dispatch({ type: "CLEAR_REFINEMENT", field: filter.key });
    } else {
      dispatch({
        type: "SET_REFINEMENT",
        field: filter.key,
        refinement: {
          field: filter.key,
          type: "terms",
          values: next,
        },
      });
    }
  };

  const setSelected = (values: string[]) => {
    if (values.length === 0) {
      dispatch({ type: "CLEAR_REFINEMENT", field: filter.key });
    } else {
      dispatch({
        type: "SET_REFINEMENT",
        field: filter.key,
        refinement: {
          field: filter.key,
          type: filter.type === "toggle" ? "toggle" : "terms",
          values,
          value: filter.type === "toggle" ? values.length > 0 : undefined,
        },
      });
    }
  };

  const filteredOptions = filter.options.filter((opt) =>
    opt.label.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-surface-shell/35 shadow-[--shadow-inset-surface]">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex min-h-11 w-full items-center justify-between gap-3 px-3.5 py-3 text-left text-sm font-medium text-foreground transition-colors hover:bg-interactive-accent-subtle/70"
      >
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate">{filter.label}</span>
          {selectedCount > 0 && (
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-accent-core/10 px-1.5 text-tiny font-semibold text-accent-core">
              {selectedCount}
            </span>
          )}
        </span>
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-border/60 px-3.5 pb-3 pt-3">
          {filter.type === "checkbox" && filter.options.length > 5 && (
            <div className="relative mb-2.5">
              <Search className="absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder={t("filter.searchPlaceholder")}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-8 w-full rounded-xl border border-border bg-surface-input/95 pl-8 pr-3 text-xs shadow-inner transition placeholder:text-muted-foreground/60 focus:border-accent-core focus:outline-none focus:ring-2 focus:ring-focus-ring"
              />
            </div>
          )}

          {filteredOptions.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/70 bg-muted/25 px-3 py-4 text-center">
              <p className="text-xs font-medium text-foreground/75">{t("filter.empty.noMatch")}</p>
              <p className="mt-1 text-tiny text-muted-foreground">
                {t("filter.empty.noMatchHint")}
              </p>
            </div>
          ) : (
            <>
              {filter.type === "chip" && (
                <div className="flex flex-wrap gap-1.5">
                  {filteredOptions.map((opt) => {
                    const isSelected = selected.includes(opt.value);
                    return (
                      <button
                        type="button"
                        key={opt.value}
                        onClick={() => toggle(opt.value)}
                        aria-pressed={isSelected}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring ${
                          isSelected
                            ? "border-accent-core bg-accent-core text-white shadow-sm"
                            : "border-border/70 bg-surface-panel text-muted-foreground hover:border-accent-core/30 hover:text-foreground"
                        }`}
                      >
                        {opt.iconKey && isFlagIcon(opt.iconKey) ? (
                          <img
                            src={getFlagSrc(opt.iconKey)!}
                            alt=""
                            width={14}
                            height={14}
                            className="inline-block"
                          />
                        ) : (
                          (() => {
                            const icon = getIcon(opt.iconKey);
                            return icon ? <span className="text-xs">{icon}</span> : null;
                          })()
                        )}
                        <span>{opt.label}</span>
                        {opt.count != null && (
                          <span
                            className={`text-tiny ${
                              isSelected ? "text-white/60" : "text-muted-foreground/60"
                            }`}
                          >
                            {opt.count.toLocaleString()}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}

              {filter.type === "checkbox" && (
                <div className="space-y-0.5">
                  {filteredOptions.map((opt) => {
                    const isSelected = selected.includes(opt.value);
                    return (
                      <label
                        key={opt.value}
                        className="flex w-full cursor-pointer items-center gap-2 rounded-xl px-2 py-1.5 transition-colors hover:bg-muted/45 group"
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          aria-checked={isSelected}
                          onChange={() => toggle(opt.value)}
                          className="sr-only"
                        />
                        <div
                          className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border transition-all ${
                            isSelected
                              ? "border-accent-core bg-accent-core"
                              : "border-border group-hover:border-muted-foreground"
                          }`}
                        >
                          {isSelected && (
                            <svg
                              className="h-2.5 w-2.5 text-white"
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                              strokeWidth={3}
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M5 13l4 4L19 7"
                              />
                            </svg>
                          )}
                        </div>
                        <span className="flex-1 text-xs text-foreground/80 transition-colors group-hover:text-foreground">
                          {opt.label}
                        </span>
                        {opt.count != null && (
                          <span className="text-tiny text-muted-foreground">
                            {opt.count.toLocaleString()}
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
              )}

              {filter.type === "dropdown" && (
                <select
                  aria-label={filter.label}
                  value={selected[0] || ""}
                  onChange={(e) => setSelected([e.target.value])}
                  className="h-9 w-full rounded-xl border border-border bg-surface-input/95 px-3 text-xs shadow-inner transition focus:border-accent-core focus:outline-none focus:ring-2 focus:ring-focus-ring"
                >
                  {filter.options.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              )}

              {filter.type === "toggle" && (
                <div className="flex items-center justify-between rounded-xl border border-border/70 bg-surface-input/70 px-3 py-2.5">
                  <button
                    type="button"
                    aria-label={`${filter.label} toggle`}
                    aria-pressed={selected.length > 0}
                    onClick={() => setSelected(selected.length > 0 ? [] : ["true"])}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelected(selected.length > 0 ? [] : ["true"]);
                      }
                    }}
                    className={`relative h-5 w-9 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring ${
                      selected.length > 0 ? "bg-accent-core" : "bg-muted-foreground/20"
                    }`}
                  >
                    <div
                      className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                        selected.length > 0 ? "translate-x-4" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                  <span className="ml-3 flex-1 text-xs text-foreground/80">
                    {filter.options[0]?.label || t("filter.yes")}
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
