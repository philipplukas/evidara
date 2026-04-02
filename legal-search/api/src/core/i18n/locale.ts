/**
 * Locale configuration and resolution.
 *
 * Parses Accept-Language headers and resolves to a supported locale.
 * ADR-0013: The BFF must accept locale input and resolve all composed
 * labels in the requested locale.
 */

/** Supported UI locales. */
export const SUPPORTED_LOCALES = ['de', 'fr'] as const;

/** The default locale when none is specified or the requested locale is unsupported. */
export const DEFAULT_LOCALE: SupportedLocale = 'de';

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

/**
 * Resolve an Accept-Language header value to a supported locale.
 *
 * Handles formats like "fr", "fr-CH", "fr-CH, de;q=0.9".
 * Returns DEFAULT_LOCALE if the header is missing, contains only
 * unsupported languages, or uses the wildcard "*".
 */
export function resolveLocale(acceptLanguage?: string): SupportedLocale {
  if (!acceptLanguage) return DEFAULT_LOCALE;

  // Parse Accept-Language into weighted entries: "fr-CH, de;q=0.9" → [{ lang: "fr", q: 1 }, { lang: "de", q: 0.9 }]
  const entries = acceptLanguage
    .split(',')
    .map((part) => {
      const [langTag, ...params] = part.trim().split(';');
      const lang = langTag.trim().split('-')[0].toLowerCase(); // "fr-CH" → "fr"
      const qParam = params.find((p) => p.trim().startsWith('q='));
      const q = qParam ? Number.parseFloat(qParam.trim().slice(2)) : 1;
      return { lang, q: Number.isNaN(q) ? 0 : q };
    })
    .sort((a, b) => b.q - a.q);

  // Find the first supported locale
  for (const entry of entries) {
    if (SUPPORTED_LOCALES.includes(entry.lang as SupportedLocale)) {
      return entry.lang as SupportedLocale;
    }
  }

  return DEFAULT_LOCALE;
}
