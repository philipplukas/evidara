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
import { useIsMobile } from "@/hooks/use-is-mobile";
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
  const isMobile = useIsMobile();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={isMobile ? "bottom" : "right"}
        className={isMobile ? "max-h-[85vh] rounded-t-2xl p-0" : "w-[90vw] sm:w-[480px] p-0"}
      >
        {isMobile && (
          <div aria-hidden="true" className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-border" />
        )}
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
