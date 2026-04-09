/**
 * BFF translation loader and resolver.
 *
 * Loads translation files at module init and provides a t() function
 * for locale-aware string resolution.
 *
 * ADR-0013: BFF owns locale-aware composition for all API-delivered
 * display labels (badges, facets, tabs, actions, metadata).
 */

import deMessages from './de.json';
import frMessages from './fr.json';
import type { SupportedLocale } from './locale';
import { DEFAULT_LOCALE } from './locale';

type TranslationMessages = Record<string, string>;

const MESSAGES: Record<SupportedLocale, TranslationMessages> = {
  de: deMessages,
  fr: frMessages,
};

/**
 * Resolve a translation key for the given locale.
 *
 * Falls back to DEFAULT_LOCALE if the key is missing in the requested locale,
 * then falls back to the key itself if missing everywhere.
 */
export function t(key: string, locale: SupportedLocale = DEFAULT_LOCALE): string {
  return MESSAGES[locale]?.[key] ?? MESSAGES[DEFAULT_LOCALE]?.[key] ?? key;
}

export function formatMessage(
  key: string,
  values: Record<string, string>,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string {
  let message = t(key, locale);
  for (const [name, value] of Object.entries(values)) {
    message = message.replaceAll(`{${name}}`, value);
  }
  return message;
}

export { DEFAULT_LOCALE, resolveLocale, type SupportedLocale } from './locale';
