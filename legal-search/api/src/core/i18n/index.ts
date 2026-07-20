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

const LANGUAGE_DISPLAY_LABELS: Record<string, string> = {
  de: 'DE',
  fr: 'FR',
  it: 'IT',
  en: 'EN',
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

/** Format a language code for compact user-facing display. */
export function formatLanguageDisplay(languageCode: string): string {
  const normalized = languageCode.trim().toLowerCase();
  return LANGUAGE_DISPLAY_LABELS[normalized] ?? normalized.toUpperCase();
}

/**
 * Format an ISO date for user-facing display as `DD.MM.YYYY`.
 *
 * Dates are rendered here rather than in the frontend for the same reason labels
 * and `formatLanguageDisplay` are: these mappers emit display-ready rows, and the
 * locale is already resolved at this boundary. Leaving the raw ISO value to the
 * client meant a German-language legal UI printed `2015-12-22` — the frontend's
 * own `formatSwissDate` existed, was tested, and had zero render sites (#761).
 *
 * Returns the input unchanged when it is not a parseable date: a value we cannot
 * interpret is shown as-is rather than silently blanked, so a malformed date is
 * visible instead of invisible.
 */
export function formatIsoDateDisplay(value: string): string {
  const trimmed = value.trim();
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(trimmed);
  if (!match) {
    return trimmed;
  }
  const [, year, month, day] = match;
  return `${day}.${month}.${year}`;
}

/** Format a lifecycle status code for user-facing display. */
export function formatLifecycleStatus(
  lifecycleStatus: string,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string {
  return t(`statuses.${lifecycleStatus.trim().toLowerCase()}`, locale);
}

export { DEFAULT_LOCALE, resolveLocale, type SupportedLocale } from './locale';
