"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { getFlagSrc, getIcon, isFlagIcon } from "@/lib/icons";
import { filterByDensity } from "@/lib/metadata-visibility";
import type { MetadataDensity, MetadataField } from "@/lib/types";
import { SectionLabel } from "../primitives";

interface MetadataListProps {
  fields: MetadataField[];
  initialDensity?: MetadataDensity;
  /** When false, omits the "Metadata" heading (e.g. glance strip in `DetailPanelHeader`). */
  showHeading?: boolean;
}

export function MetadataList({
  fields,
  initialDensity = "default",
  showHeading = true,
}: MetadataListProps) {
  const [density, setDensity] = useState<MetadataDensity>(initialDensity);
  const t = useTranslations("detail");
  const visibleFields = filterByDensity(fields, density);
  const hiddenCount = fields.length - visibleFields.length;
  const canExpand = density !== "expanded" && hiddenCount > 0;
  const canCollapse = density === "expanded" && initialDensity !== "expanded";

  if (fields.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border/70 bg-muted/25 px-4 py-5 text-center">
        <p className="text-xs font-medium text-foreground/75">{t("empty.noMetadataTitle")}</p>
        <p className="mt-1 text-tiny text-text-meta">{t("empty.noMetadataDescription")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {showHeading ? <SectionLabel>{t("metadataHeading")}</SectionLabel> : null}
      <dl className={density === "compact" ? "space-y-0.5" : "space-y-1.5"}>
        {visibleFields.map((field, i) => (
          <MetadataRow key={i} field={field} compact={density === "compact"} />
        ))}
      </dl>
      {(canExpand || canCollapse) && (
        <button
          type="button"
          aria-expanded={!canExpand}
          onClick={() => setDensity(canExpand ? "expanded" : initialDensity)}
          className="inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-tiny font-medium text-text-meta transition-colors hover:text-foreground"
        >
          {canExpand ? (
            <>
              <ChevronDown className="h-3 w-3" />
              {t("showMore", { count: hiddenCount })}
            </>
          ) : (
            <>
              <ChevronUp className="h-3 w-3" />
              {t("showLess")}
            </>
          )}
        </button>
      )}
    </div>
  );
}

function MetadataRow({ field, compact }: { field: MetadataField; compact: boolean }) {
  const hasValue = field.value.trim().length > 0;
  const t = useTranslations("detail");

  return (
    <div className={`flex items-baseline gap-2 ${compact ? "text-tiny" : "text-xs"}`}>
      <dt className="text-text-meta w-28 shrink-0 font-medium">{field.label}</dt>
      <dd
        className={
          hasValue
            ? "text-foreground/80 flex items-center gap-1 m-0"
            : "text-muted-foreground/70 italic flex items-center gap-1 m-0"
        }
      >
        {field.iconKey && isFlagIcon(field.iconKey) ? (
          <img
            src={getFlagSrc(field.iconKey)!}
            alt=""
            width={14}
            height={14}
            className="inline-block"
          />
        ) : (
          (() => {
            const icon = getIcon(field.iconKey);
            return icon ? <span className="text-sm">{icon}</span> : null;
          })()
        )}
        {hasValue ? field.value : t("notAvailable")}
      </dd>
    </div>
  );
}
