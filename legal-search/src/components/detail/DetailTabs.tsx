"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import type { TabViewModel } from "@/lib/types";

interface DetailTabsProps {
  tabs: TabViewModel[];
}

export function DetailTabs({ tabs }: DetailTabsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const activeTab = searchParams.get("tab") ?? "details";

  const setTab = useCallback(
    (key: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (key === "details") {
        params.delete("tab");
      } else {
        params.set("tab", key);
      }
      const next = params.toString();
      router.replace(next ? `${pathname}?${next}` : pathname, {
        scroll: false,
      });
    },
    [pathname, router, searchParams],
  );

  return (
    <div className="flex border-b border-border/60 px-2">
      {tabs.map((tab) => (
        <button
          type="button"
          key={tab.key}
          onClick={() => setTab(tab.key)}
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

/** Read the active tab from URL search params */
export function useActiveTab(): string {
  const searchParams = useSearchParams();
  return searchParams.get("tab") ?? "details";
}
