"use client";

import { FilterPanel } from "@/components/filters/FilterPanel";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { FilterViewModel } from "@/lib/types";

interface FiltersSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: FilterViewModel[];
}

export function FiltersSheet({ open, onOpenChange, filters }: FiltersSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-[320px] sm:w-[360px] p-0">
        <SheetHeader className="px-4 pt-4 pb-2 border-b border-border">
          <SheetTitle className="text-sm font-semibold">Filters</SheetTitle>
          <SheetDescription className="sr-only">
            Narrow search results by jurisdiction, language, court level, and more.
          </SheetDescription>
        </SheetHeader>
        <div className="overflow-y-auto h-[calc(100%-60px)]">
          <FilterPanel filters={filters} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
