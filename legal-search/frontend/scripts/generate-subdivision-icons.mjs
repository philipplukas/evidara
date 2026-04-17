#!/usr/bin/env node
/**
 * Generate src/lib/subdivisions.generated.ts from
 * contracts/vocabularies/subdivisions.json.
 *
 * The generated file is the canonical source of sub-federal data on the
 * frontend. It exports three things:
 *   - SUBDIVISION_REGISTRY: full ISO 3166-2 → entry map
 *   - SUBDIVISIONS_BY_COUNTRY: ISO 3166-1 → ordered list of ISO 3166-2
 *   - SUBDIVISION_ICONS: iconKey → iconText map (spread into icons.ts)
 *
 * Run via `npm run generate:icons`. The generated file is committed so
 * CI can assert no drift with `npm run generate:icons:check`.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const SUBDIVISIONS_PATH = resolve(REPO_ROOT, "contracts/vocabularies/subdivisions.json");
const OUTPUT_PATH = resolve(__dirname, "../src/lib/subdivisions.generated.ts");

const payload = JSON.parse(readFileSync(SUBDIVISIONS_PATH, "utf-8"));
const entries = Object.entries(payload.values);

const byCountry = new Map();
for (const [iso, entry] of entries) {
  if (!byCountry.has(entry.country)) byCountry.set(entry.country, []);
  byCountry.get(entry.country).push(iso);
}

const lines = [
  "// THIS FILE IS GENERATED. DO NOT EDIT BY HAND.",
  "// Source: contracts/vocabularies/subdivisions.json",
  "// Regenerate with: npm run generate:icons",
  "//",
  `// Covers ${entries.length} subdivisions across ${byCountry.size} countries.`,
  "",
  "export interface SubdivisionEntry {",
  "  country: string;",
  "  prefLabel: Record<string, string>;",
  "  slug: string;",
  "  iconKey: string;",
  "  iconText: string;",
  "  hierarchyTier: string;",
  "  hierarchyPath: string;",
  "  providerTokens: Record<string, string>;",
  "}",
  "",
  "export const SUBDIVISION_REGISTRY: Record<string, SubdivisionEntry> = {",
];

const sortedCountries = [...byCountry.keys()].sort();

for (const country of sortedCountries) {
  const isos = byCountry.get(country);
  lines.push(`  // ${country} — ${isos.length} entries`);
  for (const iso of isos) {
    const entry = payload.values[iso];
    const body = JSON.stringify(
      {
        country: entry.country,
        prefLabel: entry.prefLabel,
        slug: entry.slug,
        iconKey: entry.iconKey,
        iconText: entry.iconText,
        hierarchyTier: entry.hierarchyTier,
        hierarchyPath: entry.hierarchyPath,
        providerTokens: entry.providerTokens ?? {},
      },
      null,
      0,
    );
    lines.push(`  ${JSON.stringify(iso)}: ${body},`);
  }
  lines.push("");
}

lines.push("};");
lines.push("");
lines.push("export const SUBDIVISIONS_BY_COUNTRY: Record<string, readonly string[]> = {");
for (const country of sortedCountries) {
  const isos = byCountry.get(country);
  lines.push(`  ${JSON.stringify(country)}: ${JSON.stringify(isos)},`);
}
lines.push("};");
lines.push("");
lines.push("export const SUBDIVISION_ICONS: Record<string, string> = {");
for (const country of sortedCountries) {
  const isos = byCountry.get(country);
  lines.push(`  // ${country}`);
  for (const iso of isos) {
    const entry = payload.values[iso];
    lines.push(`  ${JSON.stringify(entry.iconKey)}: ${JSON.stringify(entry.iconText)},  // ${iso}`);
  }
  lines.push("");
}
lines.push("};");
lines.push("");

writeFileSync(OUTPUT_PATH, lines.join("\n"));
console.log(`Generated ${entries.length} subdivisions → ${OUTPUT_PATH}`);
