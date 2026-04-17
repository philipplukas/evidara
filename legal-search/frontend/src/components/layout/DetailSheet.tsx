"use client";

import { useTranslations } from "next-intl";
import { DetailPanel } from "@/components/detail/DetailPanel";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { DetailViewModel } from "@/lib/types";

interface DetailSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  detail: DetailViewModel | null;
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  onPin?: (id: string, title: string, type: string) => void;
  isPinned?: boolean;
}

export function DetailSheet({
  open,
  onOpenChange,
  detail,
  onFocus,
  onPivot,
  onPin,
  isPinned,
}: DetailSheetProps) {
  const t = useTranslations("detail");

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[90vw] sm:w-[480px] p-0">
        <SheetHeader className="sr-only">
          <SheetTitle>{detail?.title ?? t("empty.label")}</SheetTitle>
          <SheetDescription>{t("sheetDescription")}</SheetDescription>
        </SheetHeader>
        <div className="overflow-y-auto h-full">
          <DetailPanel
            detail={detail}
            onFocus={onFocus}
            onPivot={onPivot}
            onPin={onPin}
            isPinned={isPinned}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
