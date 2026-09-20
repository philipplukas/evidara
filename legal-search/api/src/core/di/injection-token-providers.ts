/**
 * Guard: every exported NestJS injection token must have a provider.
 *
 * ## The defect this catches
 *
 * `src/modules/documents/ports/document-content.port.ts` declared
 * `DOCUMENT_CONTENT_PORT` and an interface beside it. A `document-intelligence.
 * fetch-client.ts` implemented that interface. Nothing else in the tree referenced
 * either file: no module listed the token in `providers`, nothing `@Inject`ed it,
 * and the fetch client was imported by no one. The two files referenced only each
 * other and were, together, dead.
 *
 * That is worse than absent. A declared-and-unprovided port reads as "the wiring
 * exists, the behaviour is somewhere else", and it misled two separate diagnoses
 * of #984 — a document body read that failed was being explained by a code path
 * the running app never loads. Prose did not prevent it: the exact pair is the
 * worked example in `.claude/skills/measure-before-you-theorise/SKILL.md`, and
 * AGENTS.md's review guidance already lists "a field, config key or capability
 * declared with no producer" as a thing to flag.
 *
 * ## What is and is not decidable here
 *
 * This checks the narrow, statically-decidable shape only: a token declared as
 * `export const X = Symbol('X')` in non-test source, against `provide: X` in
 * non-test source. Nest resolves tokens at runtime through many other forms
 * (`useFactory`, dynamic modules, string tokens), and this guard deliberately
 * says nothing about those — an over-eager version would be muted within a week.
 *
 * **A provider in a spec does not count.** `src/__tests__/test-app.ts` provides
 * seven of these tokens, and a token wired only there is exactly the illusion
 * being guarded against: the tests pass, the app has no such provider.
 *
 * ## The allowlist is a debt register, not a mute button
 *
 * Entries go **stale-red**: once a listed token is provided or deleted, the
 * entry itself fails the gate. Same design as
 * `scripts/check_test_reachability.py`'s `KNOWN_UNREACHABLE`.
 *
 * It is empty, and that is not decoration — it held exactly one entry,
 * `DOCUMENT_CONTENT_PORT`, for the hours between this guard being written and
 * #1044 landing. #1044 deleted the port and its orphaned fetch client, the
 * entry went stale, `has no stale entries in the known-unprovided register`
 * went red, and the entry came out. The register did its whole job once before
 * anyone read it.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

export interface SourceFile {
  /** Path relative to the scanned root, with `/` separators. */
  path: string;
  text: string;
}

export interface TokenAudit {
  /** Every `export const X = Symbol(...)` found in non-test source. */
  declared: string[];
  /** Every token named by a `provide:` in non-test source. */
  provided: string[];
  /** Declared, not provided, not registered as known debt. */
  unprovided: string[];
  /** Registered debt that no longer describes reality — remove the entry. */
  staleAllowlist: string[];
}

/**
 * Tokens that are knowingly unprovided right now, each with the reason and the
 * change that clears it. Every entry must go red once it stops being true, so
 * an entry is a dated debt, never a mute.
 *
 * Format: `TOKEN_NAME: 'why it is unprovided, which change clears it, and the
 * `src/...` path it lives at'`.
 */
export const KNOWN_UNPROVIDED: Record<string, string> = {};

const TOKEN_DECLARATION = /export\s+const\s+([A-Z][A-Z0-9_]*)\s*=\s*Symbol\s*\(/g;
const TOKEN_PROVISION = /\bprovide\s*:\s*([A-Z][A-Z0-9_]*)\b/g;

/** Test scaffolding, whose providers are not the application's providers. */
export function isTestFile(path: string): boolean {
  return (
    path.endsWith('.spec.ts') ||
    path.endsWith('.test.ts') ||
    path.includes('__tests__/') ||
    path.includes('__mocks__/')
  );
}

function matchAll(text: string, pattern: RegExp): string[] {
  const found: string[] = [];
  // Fresh lastIndex per call: the module-level regexes carry /g state.
  pattern.lastIndex = 0;
  let match = pattern.exec(text);
  while (match !== null) {
    found.push(match[1]);
    match = pattern.exec(text);
  }
  return found;
}

/** Walk a directory for `.ts` sources, skipping generated output. */
export function readSourceFiles(root: string): SourceFile[] {
  const files: SourceFile[] = [];
  const walk = (dir: string, prefix: string): void => {
    for (const entry of readdirSync(dir).sort()) {
      if (entry === 'node_modules' || entry === 'generated') continue;
      const absolute = join(dir, entry);
      const relative = prefix ? `${prefix}/${entry}` : entry;
      if (statSync(absolute).isDirectory()) {
        walk(absolute, relative);
      } else if (entry.endsWith('.ts')) {
        files.push({ path: relative, text: readFileSync(absolute, 'utf8') });
      }
    }
  };
  walk(root, '');
  return files;
}

export function auditInjectionTokens(
  files: SourceFile[],
  allowlist: Record<string, string> = KNOWN_UNPROVIDED,
): TokenAudit {
  const declared = new Set<string>();
  const provided = new Set<string>();

  for (const file of files) {
    if (isTestFile(file.path)) continue;
    for (const token of matchAll(file.text, TOKEN_DECLARATION)) declared.add(token);
    for (const token of matchAll(file.text, TOKEN_PROVISION)) provided.add(token);
  }

  const unprovided = [...declared].filter((token) => !provided.has(token) && !(token in allowlist));
  const staleAllowlist = Object.keys(allowlist).filter(
    (token) => !declared.has(token) || provided.has(token),
  );

  return {
    declared: [...declared].sort(),
    provided: [...provided].sort(),
    unprovided: unprovided.sort(),
    staleAllowlist: staleAllowlist.sort(),
  };
}
