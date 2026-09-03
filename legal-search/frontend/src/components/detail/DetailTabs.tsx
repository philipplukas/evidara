"use client";

import { useQueryState } from "nuqs";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AnalyticsEvent, track } from "@/lib/analytics";
import { searchParamsParsers } from "@/lib/search-params";
import type { TabViewModel } from "@/lib/types";

interface DetailTabsProps {
  tabs: TabViewModel[];
}

export function DetailTabs({ tabs }: DetailTabsProps) {
  const [activeTab, setActiveTab] = useQueryState("tab", searchParamsParsers.tab);

  return (
    <div className="border-b border-border/60 px-3 py-2">
      <Tabs
        value={activeTab}
        onValueChange={(value) => {
          track(AnalyticsEvent.DETAIL_TAB_CHANGED, { tab: value, previousTab: activeTab });
          setActiveTab(value === "details" ? null : value);
        }}
      >
        <TabsList variant="line" className="h-auto w-full justify-start gap-1 p-0">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.key}
              value={tab.key}
              // Sprint 1: detail-panel tabs surface transient "which subview"
              // state — use accent-core (violet) so they're distinct from
              // the navy brand that marks identity (logo, primary CTAs, result
              // list selection). See design-system.md → Accent-core family.
              className="group gap-1.5 rounded-none border-b-2 px-3 py-2 text-xs font-medium transition-[color,font-weight,border-color] data-[state=inactive]:border-transparent data-[state=inactive]:text-muted-foreground/70 data-[state=active]:border-accent-core data-[state=active]:font-bold data-[state=active]:text-accent-core"
            >
              <span>{tab.label}</span>
              {tab.count != null && (
                <span className="rounded-full px-1.5 py-0.5 text-tiny font-semibold group-data-[state=active]:bg-accent-core-subtle group-data-[state=active]:text-accent-core bg-muted text-muted-foreground/70">
                  {tab.count}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabs.map((tab) => (
          <TabsContent
            key={`${tab.key}-panel`}
            value={tab.key}
            forceMount
            hidden={activeTab !== tab.key}
            tabIndex={activeTab === tab.key ? 0 : -1}
            className="m-0 min-h-0 border-0 p-0 shadow-none outline-none data-[state=inactive]:hidden"
            aria-hidden={activeTab !== tab.key}
          />
        ))}
      </Tabs>
    </div>
  );
}

export function useActiveTab(): string {
  const [tab] = useQueryState("tab", searchParamsParsers.tab);
  return tab;
}
