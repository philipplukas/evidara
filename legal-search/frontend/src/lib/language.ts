/**
 * Language code type matching `contracts/vocabularies/language.json`.
 *
 * ISO 639-1 two-letter codes for the languages Evidara surfaces. Kept
 * tight to the vocabulary so mapper code paths cannot branch on an
 * unrecognized code.
 */

export type LanguageCode = "de" | "fr" | "it" | "en" | "rm";

export const SUPPORTED_LANGUAGES: readonly LanguageCode[] = ["de", "fr", "it", "en", "rm"] as const;

export function isLanguageCode(value: unknown): value is LanguageCode {
  return typeof value === "string" && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}
