"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { FilterViewModel } from "@/lib/types";
import { getIcon } from "@/lib/icons";

interface FilterPanelProps {
  filters: FilterViewModel[];
}

export function FilterPanel({ filters }: FilterPanelProps) {
  return (
    <div className="py-4 space-y-1">
      <div className="px-4 pb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Filters
        </h3>
      </div>
      {filters.map((filter) => (
        <FilterGroup key={filter.key} filter={filter} />
      ))}
    </div>
  );
}

function FilterGroup({ filter }: { filter: FilterViewModel }) {
  const { state: constraints, dispatch } = useSearchConstraints();
  const [expanded, setExpanded] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  // Read selected values from the constraints provider
  const refinement = constraints.refinements.find(
    (r) => r.field === filter.key
  );
  const selected = refinement?.values ?? filter.selected;

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
    opt.label.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="border-b border-border/60 last:border-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full px-4 py-2.5 text-sm font-medium
          text-foreground hover:bg-muted/50 transition-colors"
      >
        <span>{filter.label}</span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="px-4 pb-3">
          {filter.type === "checkbox" && filter.options.length > 5 && (
            <div className="relative mb-2">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full h-7 pl-7 pr-2 text-xs rounded border border-border bg-white
                  focus:outline-none focus:ring-1 focus:ring-[#2563eb]/30"
              />
            </div>
          )}

          {filter.type === "chip" && (
            <div className="flex flex-wrap gap-1.5">
              {filteredOptions.map((opt) => {
                const icon = getIcon(opt.iconKey);
                const isSelected = selected.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    onClick={() => toggle(opt.value)}
                    className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium transition-all
                      ${
                        isSelected
                          ? "bg-[#1a2332] text-white"
                          : "bg-muted text-muted-foreground hover:text-foreground"
                      }`}
                  >
                    {icon && <span className="text-xs">{icon}</span>}
                    {opt.label}
                    {opt.count != null && (
                      <span className={`text-[10px] ${isSelected ? "text-white/60" : "text-muted-foreground/60"}`}>
                        {opt.count.toLocaleString()}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {filter.type === "checkbox" && (
            <div className="space-y-1">
              {filteredOptions.map((opt) => {
                const isSelected = selected.includes(opt.value);
                return (
                  <label
                    key={opt.value}
                    className="flex items-center gap-2 py-1 cursor-pointer group"
                  >
                    <div
                      className={`w-3.5 h-3.5 rounded border flex items-center justify-center flex-shrink-0 transition-all
                        ${
                          isSelected
                            ? "bg-[#2563eb] border-[#2563eb]"
                            : "border-border group-hover:border-muted-foreground"
                        }`}
                    >
                      {isSelected && (
                        <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <span className="text-xs text-foreground/80 group-hover:text-foreground flex-1">
                      {opt.label}
                    </span>
                    {opt.count != null && (
                      <span className="text-[10px] text-muted-foreground">
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
              value={selected[0] || ""}
              onChange={(e) => setSelected([e.target.value])}
              className="w-full h-8 px-2 text-xs rounded border border-border bg-white
                focus:outline-none focus:ring-1 focus:ring-[#2563eb]/30"
            >
              {filter.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          )}

          {filter.type === "toggle" && (
            <label className="flex items-center gap-2 cursor-pointer">
              <div
                onClick={() =>
                  setSelected(selected.length > 0 ? [] : ["true"])
                }
                className={`w-8 h-4.5 rounded-full relative transition-colors cursor-pointer
                  ${selected.length > 0 ? "bg-[#2563eb]" : "bg-muted-foreground/20"}`}
              >
                <div
                  className={`absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white shadow transition-transform
                    ${selected.length > 0 ? "translate-x-4" : "translate-x-0.5"}`}
                />
              </div>
              <span className="text-xs text-foreground/80">
                {filter.options[0]?.label || "Yes"}
              </span>
            </label>
          )}
        </div>
      )}
    </div>
  );
}
