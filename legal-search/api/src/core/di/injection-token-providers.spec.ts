/**
 * This spec IS the gate. It runs in `npm run test`, which `npm run check` runs,
 * which CI runs — the same wiring `mapping-drift.integration.spec.ts` uses.
 *
 * Delete `injection-token-providers.ts` and this file goes red on import.
 * Re-add an unprovided token and `the api surface has no unprovided injection
 * tokens` goes red.
 *
 * Per AGENTS.md's classifier rule, the cases below come from two places: hand-
 * built fixtures whose correct answer is obvious by inspection, and the real
 * `src/` tree this guard actually classifies — including one token whose
 * provider is established by reading the module file, not by asking the scanner.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  auditInjectionTokens,
  isTestFile,
  KNOWN_UNPROVIDED,
  readSourceFiles,
  type SourceFile,
} from './injection-token-providers';

const SRC_ROOT = join(process.cwd(), 'src');

const file = (path: string, text: string): SourceFile => ({ path, text });

describe('injection token provider audit — fixtures', () => {
  it('flags a token that is declared and provided by nothing', () => {
    const audit = auditInjectionTokens(
      [file('modules/x/ports/x.port.ts', "export const X_PORT = Symbol('X_PORT');")],
      {},
    );
    expect(audit.declared).toEqual(['X_PORT']);
    expect(audit.unprovided).toEqual(['X_PORT']);
  });

  it('accepts a token a module provides', () => {
    const audit = auditInjectionTokens(
      [
        file('modules/x/x.repository.ts', "export const X_REPO = Symbol('X_REPO');"),
        file('modules/x/x.module.ts', 'providers: [{ provide: X_REPO, useClass: XAdapter }]'),
      ],
      {},
    );
    expect(audit.unprovided).toEqual([]);
  });

  it('does not accept a token that only a spec provides', () => {
    // The #984 illusion in miniature: green tests, no provider in the app.
    const audit = auditInjectionTokens(
      [
        file('modules/x/ports/x.port.ts', "export const X_PORT = Symbol('X_PORT');"),
        file('__tests__/test-app.ts', '{ provide: X_PORT, useValue: stub }'),
        file('modules/x/x.service.spec.ts', '{ provide: X_PORT, useValue: stub }'),
      ],
      {},
    );
    expect(audit.unprovided).toEqual(['X_PORT']);
  });

  it('reports an allowlist entry as stale once the token is provided', () => {
    const audit = auditInjectionTokens(
      [
        file('modules/x/ports/x.port.ts', "export const X_PORT = Symbol('X_PORT');"),
        file('modules/x/x.module.ts', '{ provide: X_PORT, useClass: XAdapter }'),
      ],
      { X_PORT: 'known debt' },
    );
    expect(audit.unprovided).toEqual([]);
    expect(audit.staleAllowlist).toEqual(['X_PORT']);
  });

  it('reports an allowlist entry as stale once the token is deleted', () => {
    const audit = auditInjectionTokens([file('modules/x/x.module.ts', 'nothing here')], {
      X_PORT: 'known debt',
    });
    expect(audit.staleAllowlist).toEqual(['X_PORT']);
  });

  it('classifies test scaffolding as test scaffolding', () => {
    expect(isTestFile('modules/x/x.service.spec.ts')).toBe(true);
    expect(isTestFile('__tests__/test-app.ts')).toBe(true);
    expect(isTestFile('modules/x/x.module.ts')).toBe(false);
  });
});

describe('injection token provider audit — the real api surface', () => {
  const files = readSourceFiles(SRC_ROOT);
  const audit = auditInjectionTokens(files);

  it('scans a non-empty tree', () => {
    // A scanner that silently found nothing would pass every assertion below.
    expect(files.length).toBeGreaterThan(50);
    expect(audit.declared.length).toBeGreaterThan(5);
  });

  it('agrees with a provider read straight out of the module file', () => {
    // Independent oracle: SEARCH_REPOSITORY's provider is asserted by reading
    // search.module.ts, not by trusting the scanner that produced `provided`.
    const moduleText = readFileSync(join(SRC_ROOT, 'modules/search/search.module.ts'), 'utf8');
    expect(moduleText).toContain('provide: SEARCH_REPOSITORY');
    expect(audit.declared).toContain('SEARCH_REPOSITORY');
    expect(audit.provided).toContain('SEARCH_REPOSITORY');
  });

  it('has no unprovided injection tokens', () => {
    expect(audit.unprovided).toEqual([]);
  });

  it('has no stale entries in the known-unprovided register', () => {
    // Each entry names the change that clears it; when that change lands, the
    // entry must be deleted rather than left as a permanent mute.
    expect(audit.staleAllowlist).toEqual([]);
  });

  it('keeps every known-unprovided entry pointed at a real file', () => {
    // Vacuous while the register is empty, and deliberately so: the register's
    // teeth are the staleness rule, which the fixture cases above exercise
    // directly. This only stops an entry from naming a file that is not there.
    for (const token of Object.keys(KNOWN_UNPROVIDED)) {
      const reason = KNOWN_UNPROVIDED[token];
      const referenced = reason.match(/src\/[\w./-]+\.ts/g) ?? [];
      expect(referenced.length).toBeGreaterThan(0);
      for (const path of referenced) {
        expect(existsSync(join(process.cwd(), path)), `${token}: ${path} is gone`).toBe(true);
      }
    }
  });
});
