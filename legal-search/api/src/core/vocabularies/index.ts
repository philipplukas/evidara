/**
 * Vocabulary loader.
 *
 * Loads controlled vocabulary definitions from contracts/vocabularies/*.json
 * at module initialization. Mapper lookup tables validate against these values
 * rather than maintaining independent copies.
 *
 * ADR-0012: "Mapper lookup tables in the BFF are loaded from or validated
 * against vocabulary files, not maintained as independent copies."
 */
import * as fs from 'node:fs';
import * as path from 'node:path';

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

/** Document type labels keyed by normalized value. */
export const DOCUMENT_TYPE_LABELS: Record<string, string> = {};
for (const [key, entry] of Object.entries(docTypeVocab.properties.values.properties)) {
  DOCUMENT_TYPE_LABELS[key] =
    (entry as { properties?: { label?: { const?: string } } }).properties?.label?.const ?? key;
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

/** Jurisdiction metadata keyed by code. */
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
