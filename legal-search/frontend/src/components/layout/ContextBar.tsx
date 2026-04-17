"use client";

import { ChevronDown, Shield } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { getFlagAlt, getFlagSrc, getIcon, isFlagIcon } from "@/lib/icons";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { SearchContextViewModel } from "@/lib/types";

interface ContextBarProps {
  context: SearchContextViewModel;
}

const SOURCE_TYPE_I18N_KEYS = new Set(["all", "law", "decision", "rechtssatz", "commentary"]);

function useActiveFilterCount(constraints: {
  jurisdictions: string[];
  languages: string[];
  sourceType: string | null;
  officialOnly: boolean;
}) {
  let count = constraints.jurisdictions.length + constraints.languages.length;
  if (constraints.sourceType) count += 1;
  if (constraints.officialOnly) count += 1;
  return count;
}

/**
 * Top-level, high-signal search constraints.
 * Reads/writes through SearchConstraintsProvider dispatch actions.
 * On mobile (<md) the filter chips are collapsed behind a summary toggle.
 */
export function ContextBar({ context }: ContextBarProps) {
  const { state: constraints, dispatch } = useSearchConstraints();
  const t = useTranslations();
  const tSourceTypes = useTranslations("results.sourceTypes");
  const [mobileExpanded, setMobileExpanded] = useState(false);
  const activeCount = useActiveFilterCount(constraints.context);

  const translatedSourceTypes = context.sourceTypes.map((item) => ({
    ...item,
    label: SOURCE_TYPE_I18N_KEYS.has(item.key)
      ? tSourceTypes(item.key as "all" | "law" | "decision" | "rechtssatz" | "commentary")
      : item.label,
  }));

  const chipContent = (
    <div className="context-bar__clusters min-w-0 flex-1">
      <div className="context-bar__cluster">
        <ChipGroup
          items={context.jurisdictions.map((j) => ({
            ...j,
            active: constraints.context.jurisdictions.includes(j.key),
          }))}
          onToggle={(key) => dispatch({ type: "TOGGLE_JURISDICTION", jurisdiction: key })}
        />
      </div>

      <div className="context-bar__cluster">
        <ChipGroup
          items={context.languages.map((l) => ({
            ...l,
            active: constraints.context.languages.includes(l.key),
          }))}
          onToggle={(key) => dispatch({ type: "TOGGLE_LANGUAGE", language: key })}
        />
      </div>

      <div className="context-bar__cluster">
        <TabGroup
          items={translatedSourceTypes.map((st) => ({
            ...st,
            active:
              constraints.context.sourceType === st.key ||
              (constraints.context.sourceType === null && st.key === "all"),
          }))}
          onSelect={(key) =>
            dispatch({
              type: "SET_SOURCE_TYPE",
              sourceType: key === "all" ? null : key,
            })
          }
        />
      </div>

      <div className="context-bar__cluster">
        <button
          type="button"
          onClick={() =>
            dispatch({
              type: "SET_OFFICIAL_ONLY",
              value: !constraints.context.officialOnly,
            })
          }
          className={`context-bar__official-toggle ${
            constraints.context.officialOnly
              ? "context-bar__official-toggle--active border-accent-core/30 bg-accent-core-subtle text-accent-core"
              : "context-bar__official-toggle--idle border border-transparent text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground"
          }`}
        >
          <Shield className="h-3.5 w-3.5" />
          {t("context.officialSourcesOnly")}
        </button>
      </div>
    </div>
  );

  return (
    <div className="context-bar">
      <div className="context-bar__layout">
        {/* Desktop: always-visible label */}
        <span className="hidden text-micro shrink-0 font-medium text-muted-foreground md:block">
          {t("filter.filtersTitle")}
        </span>

        {/* Mobile: collapsible toggle */}
        <button
          type="button"
          className="flex items-center gap-1.5 text-micro font-medium text-muted-foreground md:hidden"
          onClick={() => setMobileExpanded((v) => !v)}
          aria-expanded={mobileExpanded}
        >
          {t("filter.filtersTitle")}
          {activeCount > 0 && (
            <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-core px-1 text-[10px] font-semibold text-white">
              {activeCount}
            </span>
          )}
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform duration-200 ${mobileExpanded ? "rotate-180" : ""}`}
          />
        </button>

        {/* Desktop: always show chips */}
        <div className="hidden md:contents">{chipContent}</div>

        {/* Mobile: collapsible chips */}
        {mobileExpanded && <div className="md:hidden">{chipContent}</div>}

        <button
          type="button"
          className="text-micro shrink-0 rounded-sm px-1 py-0.5 font-medium text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          onClick={() => dispatch({ type: "RESET_ALL" })}
        >
          {t("filter.resetAll")}
        </button>
      </div>
    </div>
  );
}

function ChipGroup({
  items,
  onToggle,
}: {
  items: { key: string; label: string; active: boolean; iconKey?: string }[];
  onToggle: (key: string) => void;
}) {
  return (
    <div className="context-bar__chip-group">
      {items.map((item) => {
        return (
          <button
            type="button"
            key={item.key}
            onClick={() => onToggle(item.key)}
            className={`context-bar__chip ${
              item.active
                ? "context-bar__chip--active bg-accent-core text-white shadow-sm ring-1 ring-accent-core/10"
                : "context-bar__chip--idle bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            }`}
          >
            {item.iconKey && isFlagIcon(item.iconKey) ? (
              <img
                src={getFlagSrc(item.iconKey)!}
                alt=""
                width={14}
                height={14}
                className="inline-block"
              />
            ) : (
              (() => {
                const icon = getIcon(item.iconKey);
                return icon ? <span className="text-sm leading-none">{icon}</span> : null;
              })()
            )}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

function TabGroup({
  items,
  onSelect,
}: {
  items: { key: string; label: string; active: boolean }[];
  onSelect: (key: string) => void;
}) {
  return (
    <div className="context-bar__tab-group">
      {items.map((item) => (
        <button
          type="button"
          key={item.key}
          onClick={() => onSelect(item.key)}
          className={`context-bar__tab ${
            item.active
              ? "context-bar__tab--active bg-accent-core-subtle text-accent-core ring-1 ring-accent-core/15"
              : "context-bar__tab--idle text-muted-foreground hover:bg-muted hover:text-foreground"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
