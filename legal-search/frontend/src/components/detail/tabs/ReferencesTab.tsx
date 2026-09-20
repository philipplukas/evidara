"use client";

import { useTranslations } from "next-intl";
import type { ReferenceGroup } from "@/lib/types";
import { SectionLabel } from "../../primitives";
import { ReferenceGroupList } from "../ReferenceGroupList";
import { TabEmptyState } from "./TabEmptyState";

interface ReferencesTabProps {
  references: ReferenceGroup[];
  onFocus?: (id: string) => void;
  onPivot?: (label: string, sourceId: string) => void;
  sourceId: string;
  sourceTitle: string;
}

/**
 * Preview surface for references.
 * "Show all" is the escape hatch → PIVOT → center panel context switch.
 *
 * The rows themselves live in `ReferenceGroupList`, shared with the reading
 * mode evidence rail (#1053) so the unresolved-citation guard has one home.
 */
export function ReferencesTab({
  references,
  onFocus,
  onPivot,
  sourceId,
  sourceTitle,
}: ReferencesTabProps) {
  const t = useTranslations("detail");
  if (references.length === 0) {
    return (
      <TabEmptyState
        title={t("empty.noReferencesTitle")}
        description={t("empty.noReferencesDescription")}
      />
    );
  }

  return (
    <div className="space-y-5 px-5 py-5">
      <div className="space-y-1">
        <SectionLabel>{t("tabs.references")}</SectionLabel>
        <p className="max-w-2xl text-xs leading-5 text-muted-foreground">
          {t("descriptions.references")}
        </p>
      </div>

      <ReferenceGroupList
        references={references}
        onFocus={onFocus}
        onPivot={onPivot}
        sourceId={sourceId}
        sourceTitle={sourceTitle}
      />
    </div>
  );
}
