"use client";

import { BookOpen } from "lucide-react";
import { useTranslations } from "next-intl";
import type { KeyboardEvent } from "react";
import type { LocalStructureItem } from "@/lib/types";
import { SectionLabel } from "../../primitives";
import { TabEmptyState } from "./TabEmptyState";

interface StructureTabProps {
  items: LocalStructureItem[];
  onFocus?: (id: string) => void;
}

export function StructureTab({ items, onFocus }: StructureTabProps) {
  const t = useTranslations("detail");
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, id: string) => {
    if (!onFocus) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onFocus(id);
    }
  };

  if (items.length === 0) {
    return (
      <TabEmptyState
        title={t("empty.noStructureTitle")}
        description={t("empty.noStructureDescription")}
      />
    );
  }

  return (
    <div className="space-y-3 px-5 py-5">
      <div className="space-y-1">
        <SectionLabel>{t("tabs.localStructure")}</SectionLabel>
        <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
          {t("descriptions.structure")}
        </p>
      </div>

      <div className="space-y-1">
        {items.map((item) => (
          <button
            type="button"
            key={item.id}
            onClick={() => onFocus?.(item.id)}
            onKeyDown={(event) => handleKeyDown(event, item.id)}
            aria-pressed={item.active}
            className={`flex w-full items-center gap-3 rounded-xl border-l-2 px-3 py-2.5 text-left text-xs transition-all
              ${
                item.active
                  ? "border-l-accent-core bg-accent-core-subtle text-accent-core font-semibold shadow-inset-surface"
                  : "border-l-transparent text-foreground/75 hover:bg-muted/50 hover:text-foreground"
              }`}
          >
            <BookOpen className="h-3 w-3 shrink-0" />
            <span className="min-w-0 flex-1 truncate">{item.label}</span>
            {item.active && (
              <span className="rounded-full bg-accent-core-subtle px-1.5 py-0.5 text-tiny font-semibold text-accent-core">
                {t("tabs.current")}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
