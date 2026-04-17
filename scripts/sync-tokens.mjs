#!/usr/bin/env node
/**
 * Sync the canonical design tokens at styles/tokens/ into each app's
 * src/lib/tokens/ directory.
 *
 * Why the copy? Each frontend's Docker build context is narrowed to its own
 * directory (see docker-compose*.yml), so relative imports into repo-root
 * `styles/tokens/` don't survive container builds. Until build contexts are
 * widened (follow-up), we treat the app-local copies as generated artifacts
 * and enforce drift in CI.
 *
 * Usage:
 *   node scripts/sync-tokens.mjs           # write (default)
 *   node scripts/sync-tokens.mjs --check   # exit 1 if any dest file drifts
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE_DIR = join(REPO_ROOT, "styles", "tokens");

const TARGETS = [
  join(REPO_ROOT, "platform-control", "admin", "src", "lib", "tokens"),
  join(REPO_ROOT, "legal-search", "frontend", "src", "lib", "tokens"),
];

const FILES = ["tokens.ts", "tokens.css"];

const BANNER_TS = `/**
 * GENERATED — DO NOT EDIT.
 *
 * Mirror of styles/tokens/tokens.ts. Edit the source and run:
 *   node scripts/sync-tokens.mjs
 * CI enforces drift via scripts/sync-tokens.mjs --check.
 */

`;

const BANNER_CSS = `/**
 * GENERATED — DO NOT EDIT.
 *
 * Mirror of styles/tokens/tokens.css. Edit the source and run:
 *   node scripts/sync-tokens.mjs
 * CI enforces drift via scripts/sync-tokens.mjs --check.
 */

`;

function render(file) {
  const source = readFileSync(join(SOURCE_DIR, file), "utf8");
  const banner = file.endsWith(".ts") ? BANNER_TS : BANNER_CSS;
  return banner + source;
}

const checkOnly = process.argv.includes("--check");
const drift = [];

for (const target of TARGETS) {
  if (!checkOnly) {
    mkdirSync(target, { recursive: true });
  }
  for (const file of FILES) {
    const dest = join(target, file);
    const rendered = render(file);
    if (checkOnly) {
      const current = existsSync(dest) ? readFileSync(dest, "utf8") : null;
      if (current !== rendered) {
        drift.push(dest);
      }
    } else {
      writeFileSync(dest, rendered);
      console.log(`wrote ${dest}`);
    }
  }
}

if (checkOnly && drift.length > 0) {
  console.error("Token drift detected. Run `node scripts/sync-tokens.mjs` and commit:");
  for (const path of drift) {
    console.error(`  ${path}`);
  }
  process.exit(1);
}
