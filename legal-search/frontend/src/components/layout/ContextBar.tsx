"use client";

import { Shield } from "lucide-react";
import { useTranslations } from "next-intl";
import { getIcon } from "@/lib/icons";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { SearchContextViewModel } from "@/lib/types";

interface ContextBarProps {
  context: SearchContextViewModel;
}

/**
 * Top-level, high-signal search constraints.
 * Reads/writes through SearchConstraintsProvider dispatch actions.
 */
export function ContextBar({ context }: ContextBarProps) {
  const { state: constraints, dispatch } = useSearchConstraints();
  const t = useTranslations();

  return (
    <div className="context-bar">
      <div className="context-bar__layout">
        <div className="context-bar__clusters">
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
              items={context.sourceTypes.map((t) => ({
                ...t,
                active:
                  constraints.context.sourceType === t.key ||
                  (constraints.context.sourceType === null && t.key === "all"),
              }))}
              onSelect={(key) =>
                dispatch({
                  type: "SET_SOURCE_TYPE",
                  sourceType: key === "all" ? null : key,
                })
              }
            />
          </div>
        </div>

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
              ? "context-bar__official-toggle--active border-brand/20 bg-interactive-accent-subtle text-brand"
              : "context-bar__official-toggle--idle border border-transparent text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground"
          }`}
        >
          <Shield className="h-3.5 w-3.5" />
          {t("context.officialSourcesOnly")}
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
        const icon = getIcon(item.iconKey);
        return (
          <button
            type="button"
            key={item.key}
            onClick={() => onToggle(item.key)}
            className={`context-bar__chip ${
              item.active
                ? "context-bar__chip--active bg-brand-strong text-white shadow-sm ring-1 ring-brand/10"
                : "context-bar__chip--idle bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            }`}
          >
            {icon && <span className="text-sm leading-none">{icon}</span>}
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
              ? "context-bar__tab--active bg-interactive-accent-subtle text-brand ring-1 ring-brand/10"
              : "context-bar__tab--idle text-muted-foreground hover:bg-muted hover:text-foreground"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
