"use client";

import { useTranslations } from "next-intl";
import { FilterBar } from "@/components/filters/FilterBar";
import { FilterPanel } from "@/components/filters/FilterPanel";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { useSearchConstraints } from "@/lib/search-constraints-store";
import type { FilterViewModel } from "@/lib/types";

interface FiltersSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: FilterViewModel[];
}

export function FiltersSheet({ open, onOpenChange, filters }: FiltersSheetProps) {
  const t = useTranslations("filter");
  const { dispatch } = useSearchConstraints();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="left"
        className="flex h-full max-h-screen w-[320px] flex-col p-0 sm:w-[360px]"
      >
        <SheetHeader className="border-b border-border px-4 pb-2 pt-4">
          <SheetTitle className="text-sm font-semibold">{t("filtersTitle")}</SheetTitle>
          <SheetDescription className="sr-only">{t("sheetDescription")}</SheetDescription>
        </SheetHeader>
        <FilterBar filters={filters} />
        <div className="min-h-0 flex-1 overflow-y-auto">
          <FilterPanel filters={filters} />
        </div>
        <div className="border-t border-border px-4 py-3">
          <button
            type="button"
            onClick={() => dispatch({ type: "RESET_ALL" })}
            className="text-xs font-medium text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline"
          >
            {t("resetAll")}
          </button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
