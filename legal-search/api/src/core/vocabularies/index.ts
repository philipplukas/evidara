/**
 * Vocabulary loader.
 *
 * Loads controlled vocabulary definitions from contracts/vocabularies/*.json
 * at module initialization. Provides both static label maps (for backward
 * compat) and locale-aware resolution functions (ADR-0013).
 *
 * ADR-0012: "Mapper lookup tables in the BFF are loaded from or validated
 * against vocabulary files, not maintained as independent copies."
 */
import * as fs from 'node:fs';
import * as path from 'node:path';
import type { SupportedLocale } from '../i18n/locale';
import { DEFAULT_LOCALE } from '../i18n/locale';

interface DocumentTypeEntry {
  label: string;
  aliases: string[];
  sortOrder: number;
}

interface JurisdictionEntry {
  label: string;
  iconKey: string;
  standard: string;
}

// ─── Load vocabulary files ───

const VOCAB_DIR = path.resolve(__dirname, '../../../../../contracts/vocabularies');

function loadVocabFile(filename: string): Record<string, unknown> {
  const filePath = path.join(VOCAB_DIR, filename);
  const raw = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(raw);
}

// ─── Document Type Vocabulary ───

const docTypeVocab = loadVocabFile('document-type.json') as {
  properties: {
    values: {
      properties: Record<string, { properties: DocumentTypeEntry }>;
    };
  };
};

/** Valid normalized document type values. */
export const DOCUMENT_TYPE_VALUES = Object.keys(docTypeVocab.properties.values.properties);

/** Document type labels keyed by normalized value (default locale). */
export const DOCUMENT_TYPE_LABELS: Record<string, string> = {};
for (const [key, entry] of Object.entries(docTypeVocab.properties.values.properties)) {
  DOCUMENT_TYPE_LABELS[key] =
    (entry as { properties?: { label?: { const?: string } } }).properties?.label?.const ?? key;
}

/** Locale-keyed document type labels loaded from vocabulary. */
const DOCUMENT_TYPE_LOCALE_LABELS: Record<string, Record<string, string>> = {};
for (const [key, entry] of Object.entries(docTypeVocab.properties.values.properties)) {
  const props = (
    entry as { properties?: { labels?: { properties?: Record<string, { const?: string }> } } }
  ).properties;
  const labels: Record<string, string> = {};
  if (props?.labels?.properties) {
    for (const [locale, localeEntry] of Object.entries(props.labels.properties)) {
      if (localeEntry?.const) labels[locale] = localeEntry.const;
    }
  }
  DOCUMENT_TYPE_LOCALE_LABELS[key] = labels;
}

/**
 * Resolve a document type label for the given locale.
 * Falls back: labels[locale] → labels[DEFAULT_LOCALE] → label → code.
 */
export function getDocumentTypeLabel(
  typeCode: string,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string {
  const localeLabels = DOCUMENT_TYPE_LOCALE_LABELS[typeCode];
  return (
    localeLabels?.[locale] ??
    localeLabels?.[DEFAULT_LOCALE] ??
    DOCUMENT_TYPE_LABELS[typeCode] ??
    typeCode
  );
}

// ─── Jurisdiction Vocabulary ───

const jurisdictionVocab = loadVocabFile('jurisdiction.json') as {
  properties: {
    values: {
      properties: Record<string, { properties: JurisdictionEntry }>;
    };
  };
};

/** Valid normalized jurisdiction codes. */
export const JURISDICTION_VALUES = Object.keys(jurisdictionVocab.properties.values.properties);

/** Jurisdiction metadata keyed by code (default locale). */
export const JURISDICTION_META: Record<string, { label: string; iconKey: string }> = {};
for (const [key, entry] of Object.entries(jurisdictionVocab.properties.values.properties)) {
  const props = (
    entry as {
      properties?: {
        label?: { const?: string };
        iconKey?: { const?: string };
      };
    }
  ).properties;
  JURISDICTION_META[key] = {
    label: props?.label?.const ?? key,
    iconKey: props?.iconKey?.const ?? key.toLowerCase(),
  };
}

/** Locale-keyed jurisdiction labels loaded from vocabulary. */
const JURISDICTION_LOCALE_LABELS: Record<string, Record<string, string>> = {};
for (const [key, entry] of Object.entries(jurisdictionVocab.properties.values.properties)) {
  const props = (
    entry as { properties?: { labels?: { properties?: Record<string, { const?: string }> } } }
  ).properties;
  const labels: Record<string, string> = {};
  if (props?.labels?.properties) {
    for (const [locale, localeEntry] of Object.entries(props.labels.properties)) {
      if (localeEntry?.const) labels[locale] = localeEntry.const;
    }
  }
  JURISDICTION_LOCALE_LABELS[key] = labels;
}

/**
 * Resolve a jurisdiction label for the given locale.
 * Falls back: labels[locale] → labels[DEFAULT_LOCALE] → label → code.
 */
export function getJurisdictionLabel(
  code: string,
  locale: SupportedLocale = DEFAULT_LOCALE,
): string {
  const localeLabels = JURISDICTION_LOCALE_LABELS[code];
  return (
    localeLabels?.[locale] ??
    localeLabels?.[DEFAULT_LOCALE] ??
    JURISDICTION_META[code]?.label ??
    code
  );
}

/**
 * Get jurisdiction metadata (label + iconKey) for a given locale.
 */
export function getJurisdictionMeta(
  code: string,
  locale: SupportedLocale = DEFAULT_LOCALE,
): { label: string; iconKey: string } | undefined {
  const meta = JURISDICTION_META[code];
  if (!meta) return undefined;
  return {
    label: getJurisdictionLabel(code, locale),
    iconKey: meta.iconKey,
  };
}
