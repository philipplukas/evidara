"use client";

import { parseAsString, useQueryState } from "nuqs";
import type { TabViewModel } from "@/lib/types";

interface DetailTabsProps {
  tabs: TabViewModel[];
}

export function DetailTabs({ tabs }: DetailTabsProps) {
  const [activeTab, setActiveTab] = useQueryState("tab", parseAsString.withDefault("details"));

  return (
    <div className="flex border-b border-border/60 px-2">
      {tabs.map((tab) => (
        <button
          type="button"
          key={tab.key}
          onClick={() => setActiveTab(tab.key === "details" ? null : tab.key)}
          className={`px-3 py-2.5 text-xs font-medium border-b-2 transition-colors
            ${
              activeTab === tab.key
                ? "border-brand text-brand"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
        >
          {tab.label}
          {tab.count != null && (
            <span className="ml-1 text-tiny text-muted-foreground/60">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

/** Read the active tab from URL search params via nuqs */
export function useActiveTab(): string {
  const [tab] = useQueryState("tab", parseAsString.withDefault("details"));
  return tab;
}
