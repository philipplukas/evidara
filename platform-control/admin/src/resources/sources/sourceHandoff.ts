/**
 * Shared legal-search -> source handoff guidance.
 *
 * `buildSourceHandoffGuidance` turns a resolved `LegalSearchHandoff` (read
 * from the URL by `readLegalSearchHandoff`) plus the source record into the
 * two operator-facing sentences the handoff card renders: *why you are here*
 * and *what to check next*.
 *
 * This logic is deliberately framework-agnostic (no React, no MUI, no
 * Tailwind) — separated from the Tailwind `SourceShow.tsx` detail page so the
 * guidance copy can be unit-tested in isolation (ADR-0026).
 */
import type { SourceRecord } from "../../lib/admin/dataProvider";
import {
  describeLegalSearchHandoff,
  type LegalSearchHandoff,
} from "../../lib/admin/navigationContext";

export type SourceHandoffGuidance = {
  whyYouAreHere: string;
  whatToCheckNext: string;
};

export function buildSourceHandoffGuidance(
  source: SourceRecord,
  handoff: LegalSearchHandoff,
): SourceHandoffGuidance | null {
  if (!handoff.hasOrigin) {
    return null;
  }

  const contextSummary = describeLegalSearchHandoff(handoff);
  const whyYouAreHere = `You came from legal search. ${contextSummary}.`;
  const whatToCheckNext =
    source.status === "active"
      ? `${source.name} is active, so confirm the jurisdiction, authority, and version history below before you treat it as the source behind the selected search item.`
      : source.status === "inactive"
        ? `${source.name} is inactive, so check whether it should be reactivated before any work continues on the selected search item.`
        : `${source.name} is archived, so treat the record as read-only and confirm whether the selected search item should point to a different source.`;

  return {
    whyYouAreHere,
    whatToCheckNext,
  };
}
