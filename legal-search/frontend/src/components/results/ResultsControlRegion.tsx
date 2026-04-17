"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

interface ResultsControlRegionProps {
  children: ReactNode;
  className?: string;
}

/**
 * Groups result-scoped controls (scope, exact matches, list) for semantics and ADR-0016 alignment.
 */
export function ResultsControlRegion({ children, className }: ResultsControlRegionProps) {
  const t = useTranslations("workspace");
  return (
    <section aria-label={t("resultsControlRegion")} className={className}>
      {children}
    </section>
  );
}
