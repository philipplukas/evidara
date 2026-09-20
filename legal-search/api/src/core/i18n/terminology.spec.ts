/**
 * The cross-surface terminology guard.
 *
 * This is the ONE place the two legal-search surfaces' words are compared. It
 * reads the BFF's message files and the frontend's, and fails when either
 * disagrees with `terminology.ts` — which is why that table, and not either
 * message file, is the source of truth for a shared word.
 *
 * Putting a copy of this check in each surface would reproduce the very defect
 * it exists to stop (AGENTS.md: "the same rule enforced in two clients rather
 * than once behind them"). It lives on the API side because ADR-0013 makes the
 * BFF the owner of composed display labels; it reaches across to the frontend's
 * messages the same way `core/vocabularies/index.ts` reaches into `contracts/`.
 *
 * It cannot silently abstain. A missing key is a failure, not a skip: `t()`
 * falls back to the key itself, and `readPath` throws rather than returning
 * undefined. The coverage block at the end fails if the table is emptied, if a
 * term stops binding both surfaces, or if a retired word loses its replacement
 * — so deleting the data is not a way to make the guard pass.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import { describe, expect, it } from 'vitest';
import deApi from './de.json';
import frApi from './fr.json';
import { SUPPORTED_LOCALES, type SupportedLocale } from './locale';
import { RETIRED_TERMS, SHARED_TERMS } from './terminology';

// ─── Loading both surfaces ───

const FRONTEND_MESSAGES_DIR = path.resolve(
  __dirname,
  '../../../../frontend/src/i18n/messages',
);

function loadFrontendMessages(locale: SupportedLocale): Record<string, unknown> {
  const file = path.join(FRONTEND_MESSAGES_DIR, `${locale}.json`);
  // Not a try/catch: if the frontend's messages move, this guard must go red
  // rather than quietly start checking one surface.
  return JSON.parse(fs.readFileSync(file, 'utf-8'));
}

const API_MESSAGES: Record<SupportedLocale, Record<string, string>> = {
  de: deApi,
  fr: frApi,
};

const FRONTEND_MESSAGES: Record<SupportedLocale, Record<string, unknown>> = {
  de: loadFrontendMessages('de'),
  fr: loadFrontendMessages('fr'),
};

/** Resolve a dotted path, throwing if any segment is missing. */
function readPath(messages: Record<string, unknown>, dotted: string): string {
  let node: unknown = messages;
  for (const segment of dotted.split('.')) {
    if (typeof node !== 'object' || node === null || !(segment in node)) {
      throw new Error(`frontend message path "${dotted}" does not exist`);
    }
    node = (node as Record<string, unknown>)[segment];
  }
  if (typeof node !== 'string') {
    throw new Error(`frontend message path "${dotted}" is not a string`);
  }
  return node;
}

/** Collect every string value in a (possibly nested) message object. */
function allStrings(node: unknown, trail: string[] = []): { path: string; value: string }[] {
  if (typeof node === 'string') return [{ path: trail.join('.'), value: node }];
  if (typeof node !== 'object' || node === null) return [];
  return Object.entries(node).flatMap(([key, child]) =>
    key === 'default' ? [] : allStrings(child, [...trail, key]),
  );
}

// ─── The shared vocabulary holds on both surfaces ───

describe('shared legal terminology', () => {
  for (const term of SHARED_TERMS) {
    describe(term.concept, () => {
      for (const locale of SUPPORTED_LOCALES) {
        const word = term.terms[locale];

        it.each(term.apiKeys)(`API %s says "${word}" in ${locale}`, (key) => {
          expect(API_MESSAGES[locale][key], `${key} (${locale})`).toBe(word);
        });

        for (const dotted of term.frontendKeys) {
          it(`frontend ${dotted} says "${word}" in ${locale}`, () => {
            expect(readPath(FRONTEND_MESSAGES[locale], dotted), `${dotted} (${locale})`).toBe(
              word,
            );
          });
        }

        // Prose inflects, so a phrase binding is checked against the stem.
        const stem = term.stems?.[locale] ?? word;
        for (const dotted of term.frontendPhrases) {
          it(`frontend ${dotted} uses "${stem}" in ${locale}`, () => {
            const value = readPath(FRONTEND_MESSAGES[locale], dotted);
            expect(
              value.toLowerCase(),
              `${dotted} (${locale}) reads "${value}" and must use "${stem}"`,
            ).toContain(stem.toLowerCase());
          });
        }
      }
    });
  }
});

// ─── Retired words are gone from both surfaces ───

describe('retired legal terminology', () => {
  for (const retired of RETIRED_TERMS) {
    for (const word of retired.words) {
      // \b is unreliable next to German umlauts in some engines; bound on
      // characters that cannot be part of a German or French word instead.
      const pattern = new RegExp(`(^|[^\\p{L}])${word}([^\\p{L}]|$)`, 'iu');

      it(`API ${retired.locale}.json no longer says "${word}"`, () => {
        const offenders = Object.entries(API_MESSAGES[retired.locale])
          .filter(([, value]) => pattern.test(value))
          .map(([key, value]) => `${key}: "${value}"`);
        expect(offenders, `${word} — ${retired.reason}`).toEqual([]);
      });

      it(`frontend ${retired.locale}.json no longer says "${word}"`, () => {
        const offenders = allStrings(FRONTEND_MESSAGES[retired.locale])
          .filter(({ value }) => pattern.test(value))
          .map(({ path: p, value }) => `${p}: "${value}"`);
        expect(offenders, `${word} — ${retired.reason}`).toEqual([]);
      });
    }
  }
});

// ─── The guard cannot be emptied into a pass ───

describe('terminology guard coverage', () => {
  it('checks every locale the BFF serves', () => {
    for (const term of SHARED_TERMS) {
      expect(Object.keys(term.terms).sort(), term.concept).toEqual([...SUPPORTED_LOCALES].sort());
    }
  });

  it('binds every shared term to both surfaces', () => {
    // A term naming keys on only one surface is not cross-surface, and a guard
    // over it would prove nothing about the drift this file exists to stop.
    for (const term of SHARED_TERMS) {
      expect(term.apiKeys.length, `${term.concept} has no API binding`).toBeGreaterThan(0);
      expect(
        term.frontendKeys.length + term.frontendPhrases.length,
        `${term.concept} has no frontend binding`,
      ).toBeGreaterThan(0);
    }
  });

  it('keeps every prose stem a form of its own term', () => {
    // Without this, a failing phrase check could be "fixed" by pointing the
    // stem at whatever the prose happens to say.
    for (const term of SHARED_TERMS) {
      for (const [locale, stem] of Object.entries(term.stems ?? {})) {
        const word = term.terms[locale as SupportedLocale].toLowerCase();
        expect(
          word.startsWith(stem.toLowerCase()) || stem.toLowerCase().startsWith(word),
          `${term.concept}: stem "${stem}" is not a form of "${term.terms[locale as SupportedLocale]}"`,
        ).toBe(true);
      }
    }
  });

  it('only defines a stem where a phrase binding uses it', () => {
    for (const term of SHARED_TERMS) {
      if (Object.keys(term.stems ?? {}).length > 0) {
        expect(term.frontendPhrases.length, `${term.concept} defines an unused stem`).toBeGreaterThan(
          0,
        );
      }
    }
  });

  it('gives every shared term a source', () => {
    for (const term of SHARED_TERMS) {
      expect(term.evidence.length, `${term.concept} has no evidence`).toBeGreaterThan(40);
    }
  });

  it('points every retired word at a term that replaced it', () => {
    const concepts = new Set(SHARED_TERMS.map((t) => t.concept));
    for (const retired of RETIRED_TERMS) {
      expect(retired.words.length, 'a retired entry lists no words').toBeGreaterThan(0);
      expect(concepts, `${retired.words[0]} → ${retired.replacedBy}`).toContain(
        retired.replacedBy,
      );
    }
  });

  it('still covers the concepts that drifted', () => {
    // The three that were wrong on 2026-09-20. Named explicitly so that
    // deleting a row from SHARED_TERMS fails here instead of reducing the
    // suite to a smaller, greener one.
    const concepts = SHARED_TERMS.map((t) => t.concept);
    expect(concepts).toEqual(
      expect.arrayContaining(['crossReference', 'citationLocator', 'legalOrder']),
    );
    const retiredWords = RETIRED_TERMS.flatMap((r) => r.words);
    expect(retiredWords).toEqual(
      expect.arrayContaining(['Zitationen', 'Referenzen', 'Zuständigkeit', 'Gerichtsbarkeit']),
    );
  });
});

// ─── Citation type codes are translated, not printed raw ───

describe('citation type labels', () => {
  // Measured 2026-09-20 against the production `citations` index (8,234 rows):
  // sr 4,334 · article 3,625 · ch_paragraph 234 · de_paragraph 20 ·
  // eu_directive 14 · eu_regulation 7. These are the group headings on the
  // references panel, and every one of them used to render as the raw code.
  const PRODUCTION_CITATION_TYPES = [
    'sr',
    'article',
    'ch_paragraph',
    'de_paragraph',
    'eu_directive',
    'eu_regulation',
  ];

  for (const locale of SUPPORTED_LOCALES) {
    it.each(PRODUCTION_CITATION_TYPES)(`translates %s in ${locale}`, (code) => {
      const label = API_MESSAGES[locale][`citationTypes.${code}`];
      expect(label, `citationTypes.${code} (${locale}) is missing`).toBeTruthy();
      expect(label, `citationTypes.${code} (${locale}) is still the raw code`).not.toBe(code);
    });
  }
});
