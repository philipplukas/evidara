"use client";

import { NextIntlClientProvider } from "next-intl";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo } from "react";
import { MESSAGES } from "@/i18n/messages";

// ─── Types ───

export type SupportedLocale = "de" | "fr";
export const SUPPORTED_LOCALES: SupportedLocale[] = ["de", "fr"];
export const DEFAULT_LOCALE: SupportedLocale = "de";

const STORAGE_KEY = "evidara-locale";

// ─── Context ───

interface LocaleContextValue {
  locale: SupportedLocale;
  setLocale: (locale: SupportedLocale) => void;
}

const LocaleContext = createContext<LocaleContextValue>({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
});

export function useLocale() {
  return useContext(LocaleContext);
}

// ─── Module-level accessor for non-React code (custom fetch) ───

let _currentLocale: SupportedLocale = DEFAULT_LOCALE;

/** Read the current locale from outside React (e.g., in the Orval mutator). */
export function getCurrentLocale(): SupportedLocale {
  return _currentLocale;
}

// ─── Helpers ───

function resolveInitialLocale(): SupportedLocale {
  // 1. Check localStorage
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && SUPPORTED_LOCALES.includes(stored as SupportedLocale)) {
      return stored as SupportedLocale;
    }

    // 2. Check browser language
    const browserLang = navigator.language?.split("-")[0];
    if (browserLang && SUPPORTED_LOCALES.includes(browserLang as SupportedLocale)) {
      return browserLang as SupportedLocale;
    }
  }

  // 3. Default
  return DEFAULT_LOCALE;
}

// ─── Provider ───

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useQueryState(
    "locale",
    parseAsStringLiteral(SUPPORTED_LOCALES).withDefault(resolveInitialLocale()),
  );

  const setLocale = useCallback(
    (next: SupportedLocale) => {
      setLocaleState(next);
      if (typeof window !== "undefined") {
        localStorage.setItem(STORAGE_KEY, next);
      }
    },
    [setLocaleState],
  );

  // Keep module-level variable in sync for the custom fetch mutator
  useEffect(() => {
    _currentLocale = locale;
  }, [locale]);

  // Sync <html lang="…">
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  // Persist to localStorage on initial render if from URL
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, locale);
    }
  }, [locale]);

  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);

  return (
    <LocaleContext.Provider value={value}>
      <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]}>
        {children}
      </NextIntlClientProvider>
    </LocaleContext.Provider>
  );
}
