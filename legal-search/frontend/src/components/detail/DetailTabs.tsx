"use client";

import { parseAsString, useQueryState } from "nuqs";
import type { TabViewModel } from "@/lib/types";

interface DetailTabsProps {
  tabs: TabViewModel[];
}

export function DetailTabs({ tabs }: DetailTabsProps) {
  const [activeTab, setActiveTab] = useQueryState("tab", parseAsString.withDefault("details"));

  return (
    <div className="border-b border-border/60 px-3 py-2">
      <div className="flex gap-1 overflow-x-auto rounded-2xl bg-surface-shell/40 p-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.key;

          return (
            <button
              type="button"
              key={tab.key}
              onClick={() => setActiveTab(tab.key === "details" ? null : tab.key)}
              aria-current={isActive ? "page" : undefined}
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring ${
                isActive
                  ? "bg-surface-panel text-brand shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]"
                  : "text-muted-foreground hover:bg-surface-panel/80 hover:text-foreground"
              }`}
            >
              <span>{tab.label}</span>
              {tab.count != null && (
                <span
                  className={`rounded-full px-1.5 py-0.5 text-tiny font-semibold ${
                    isActive ? "bg-brand/10 text-brand" : "bg-muted text-muted-foreground/70"
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Read the active tab from URL search params via nuqs */
export function useActiveTab(): string {
  const [tab] = useQueryState("tab", parseAsString.withDefault("details"));
  return tab;
}
