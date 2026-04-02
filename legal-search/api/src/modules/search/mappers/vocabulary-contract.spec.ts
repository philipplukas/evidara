/**
 * Vocabulary contract tests.
 *
 * Validates that BFF mapper lookup tables match the vocabulary files
 * in contracts/vocabularies/. This prevents drift between the source
 * of truth (vocabulary files) and the presentation layer (mappers).
 *
 * ADR-0012: "Mapper lookup tables in the BFF are loaded from or validated
 * against vocabulary files, not maintained as independent copies."
 */
import { describe, expect, it } from 'vitest';
import {
  DOCUMENT_TYPE_LABELS,
  DOCUMENT_TYPE_VALUES,
  JURISDICTION_META,
  JURISDICTION_VALUES,
} from '../../../core/vocabularies';

// ─── Document Type Vocabulary Completeness ───

describe('document_type vocabulary contract', () => {
  it('should have loaded document type values from vocabulary file', () => {
    expect(DOCUMENT_TYPE_VALUES.length).toBeGreaterThan(0);
  });

  it('should contain all expected normalized values', () => {
    expect(DOCUMENT_TYPE_VALUES).toContain('law');
    expect(DOCUMENT_TYPE_VALUES).toContain('decision');
    expect(DOCUMENT_TYPE_VALUES).toContain('commentary');
    expect(DOCUMENT_TYPE_VALUES).toContain('rechtssatz');
  });

  it('should have labels for every value', () => {
    for (const value of DOCUMENT_TYPE_VALUES) {
      expect(DOCUMENT_TYPE_LABELS[value]).toBeDefined();
      expect(typeof DOCUMENT_TYPE_LABELS[value]).toBe('string');
    }
  });

  it('should not have unexpected values in the vocabulary', () => {
    // The vocabulary is the source of truth — no extra values allowed
    expect(DOCUMENT_TYPE_VALUES).toHaveLength(4);
  });
});

// ─── Jurisdiction Vocabulary Completeness ───

describe('jurisdiction vocabulary contract', () => {
  it('should have loaded jurisdiction values from vocabulary file', () => {
    expect(JURISDICTION_VALUES.length).toBeGreaterThan(0);
  });

  it('should contain all expected ISO 3166-1 codes', () => {
    expect(JURISDICTION_VALUES).toContain('CH');
    expect(JURISDICTION_VALUES).toContain('AT');
    expect(JURISDICTION_VALUES).toContain('DE');
    expect(JURISDICTION_VALUES).toContain('LI');
  });

  it('should have label and iconKey for every jurisdiction', () => {
    for (const code of JURISDICTION_VALUES) {
      const meta = JURISDICTION_META[code];
      expect(meta).toBeDefined();
      expect(typeof meta.label).toBe('string');
      expect(typeof meta.iconKey).toBe('string');
    }
  });

  it('should not have unexpected values in the vocabulary', () => {
    expect(JURISDICTION_VALUES).toHaveLength(4);
  });
});

// ─── Negative: Unknown Values ───

describe('unknown vocabulary value handling', () => {
  it('should not have "statute" in document type vocabulary', () => {
    // "statute" is an alias, not a normalized value
    expect(DOCUMENT_TYPE_VALUES).not.toContain('statute');
  });

  it('should not have lowercase jurisdiction codes', () => {
    for (const code of JURISDICTION_VALUES) {
      expect(code).toBe(code.toUpperCase());
    }
  });
});
