import type { MetadataField } from "./types";

/**
 * Filter detail metadata rows by the reader's chosen density.
 *
 * `visibility` is decided by the BFF and is required on every row — see
 * `MetadataField` in `./types`. There is deliberately no client-side fallback:
 * this module used to carry label-matching rules (`/^(court|jurisdiction)$/i`)
 * that could never fire, because the BFF emits localized labels
 * ("Rechtsordnung", "In Kraft"). A display label is not a stable join key
 * across a translation boundary; adding German patterns would only have moved
 * the same defect to French (#787).
 */
export function filterByDensity(
  fields: MetadataField[],
  density: "compact" | "default" | "expanded",
): MetadataField[] {
  return fields.filter((field) => {
    if (density === "expanded") return true;
    if (density === "default") return field.visibility !== "expanded";
    return field.visibility === "always";
  });
}
