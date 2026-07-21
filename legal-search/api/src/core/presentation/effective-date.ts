/**
 * How `effective_date` is labelled, and why it is not simply "Datum" (#759).
 *
 * For a court decision the indexed `effective_date` is not the decision date. It is
 * derived upstream by scraping the first date-shaped string out of the document body,
 * so it routinely picks up a cited docket, a hearing date, or the date of a referenced
 * decision instead. A UI audit of the seeded corpus found it disagreeing with the
 * docket year on 16 of 20 documents — on `AVV.2020.54` the row read `2019-06-14` while
 * the document's own text says the decision issued 30 November 2020.
 *
 * The extraction defect is fixed separately, in document-intelligence. What is fixed
 * here is the *presentation*: a bare "Datum" with a calendar icon gives a scraped guess
 * the same visual authority as a verified field, and a confidently wrong date is worse
 * for a lawyer than an absent one. ADR-0033 §2 makes the general form of this the point
 * — "structured coverage is the only real cure for confident fabrication" — and a
 * surface must not read as more certain than the data behind it. So the value is still
 * shown (suppressing it would lose the only date signal there is) but the label carries
 * the qualifier.
 *
 * The qualifier rides on the **label**, not the value, on purpose. `ResultCard` renders
 * metadata values with `truncate` in an 11rem grid cell while the label is `shrink-0`;
 * a qualifier appended to the value would be the first thing clipped away, which is the
 * exact failure this change exists to prevent.
 *
 * Scoped to `decision` because that is where the defect is measured and where the label
 * is "Datum". Laws render the same field as "In Kraft" via a different upstream path
 * (`in_force_from` coalesces onto it) and are not implicated by #759's evidence.
 */

import type { SupportedLocale } from '../i18n';
import { t } from '../i18n';

/** True when `effective_date` for this document type is body-scraped and unverified. */
export function isEffectiveDateUnverified(documentType: string | undefined): boolean {
  return documentType === 'decision';
}

/**
 * Label for the `effective_date` metadata row.
 *
 * Decisions get the unverified-provenance qualifier; everything else keeps the
 * "In Kraft" in-force label it had.
 */
export function effectiveDateLabel(
  documentType: string | undefined,
  locale: SupportedLocale,
): string {
  if (isEffectiveDateUnverified(documentType)) {
    return t('metadata.dateUnverified', locale);
  }
  return t('metadata.inForce', locale);
}
