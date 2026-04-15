"use client";

import { parseAsString, useQueryState } from "nuqs";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { TabViewModel } from "@/lib/types";

interface DetailTabsProps {
  tabs: TabViewModel[];
}

export function DetailTabs({ tabs }: DetailTabsProps) {
  const [activeTab, setActiveTab] = useQueryState("tab", parseAsString.withDefault("details"));

  return (
    <div className="border-b border-border/60 px-3 py-2">
      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value === "details" ? null : value)}
      >
        <TabsList variant="line" className="h-auto w-full justify-start gap-1 p-0">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.key}
              value={tab.key}
              className="group gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition-[color,font-weight,opacity] data-[state=inactive]:text-muted-foreground/70 data-[state=inactive]:opacity-85 data-[state=active]:font-[var(--tab-active-font-weight)] data-[state=active]:text-foreground data-[state=active]:opacity-100"
            >
              <span>{tab.label}</span>
              {tab.count != null && (
                <span className="rounded-full px-1.5 py-0.5 text-tiny font-semibold group-data-[state=active]:bg-brand/10 group-data-[state=active]:text-brand bg-muted text-muted-foreground/70">
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
  const [tab] = useQueryState("tab", parseAsString.withDefault("details"));
  return tab;
}
