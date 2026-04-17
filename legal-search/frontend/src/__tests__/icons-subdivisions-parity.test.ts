/**
 * Icons ↔ Subdivisions Parity Test
 *
 * WHY THIS TEST EXISTS:
 * `contracts/vocabularies/subdivisions.json` is the single source of truth for
 * sub-federal identity (ISO 3166-2 code → slug, iconKey, hierarchy path, etc.).
 * `src/lib/icons.ts` duplicates the `iconKey` field as a map entry per
 * subdivision. Adding a new subdivision in the vocabulary but forgetting the
 * icon entry — or vice-versa — ships silently.
 *
 * This test asserts every `iconKey` from subdivisions.json has a matching
 * entry in the icon map. Follow-up plan: move icons.ts to build-time
 * generation from subdivisions.json, at which point this test gets replaced
 * by a round-trip assertion. See
 * docs/runbooks/country-rollout-drift-prevention-backlog.md §1.3.
 *
 * WHAT WE DON'T TEST:
 * - Icon visual correctness (text fallbacks are ISO-style letters until the
 *   SVG migration planned in design-system.md "Future Work").
 * - Country-level icon keys (`ch`, `at`, `de`, `fr`, `it`, `eu`, `li`) —
 *   those live in jurisdiction.json, not subdivisions.json.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { getIcon } from "@/lib/icons";

const REPO_ROOT = resolve(__dirname, "../../../..");
const SUBDIVISIONS_PATH = resolve(REPO_ROOT, "contracts/vocabularies/subdivisions.json");

type SubdivisionsFile = {
  values: Record<string, { iconKey: string; country: string }>;
};

function loadSubdivisions(): SubdivisionsFile {
  const raw = readFileSync(SUBDIVISIONS_PATH, "utf-8");
  return JSON.parse(raw) as SubdivisionsFile;
}

describe("icons.ts ↔ subdivisions.json parity", () => {
  /**
   * WHY: Every subdivision the BFF might hand us a key for MUST render.
   * Catches the drift class where subdivisions.json adds an entry (e.g. a
   * new country's regioni) but icons.ts never picks up the iconKey.
   */
  it("every subdivision iconKey resolves to an icon", () => {
    const { values } = loadSubdivisions();
    const missing: string[] = [];
    for (const [isoCode, entry] of Object.entries(values)) {
      if (!entry.iconKey) {
        missing.push(`${isoCode}: no iconKey field`);
        continue;
      }
      if (getIcon(entry.iconKey) === null) {
        missing.push(`${isoCode} → ${entry.iconKey}`);
      }
    }
    expect(missing, `Subdivisions missing from icons.ts:\n  ${missing.join("\n  ")}`).toEqual([]);
  });

  /**
   * WHY: iconKey values must follow the `<iso-country-lowercased>-<slug>`
   * convention, so the frontend can parse country/subdivision without
   * consulting the vocabulary at render time. Prevents ad-hoc forms like
   * `zh-ch` or `ch_zh`.
   */
  it("every subdivision iconKey follows the <country>-<slug> convention", () => {
    const { values } = loadSubdivisions();
    const violations: string[] = [];
    for (const [isoCode, entry] of Object.entries(values)) {
      const expected = `${entry.country.toLowerCase()}-`;
      if (!entry.iconKey.startsWith(expected)) {
        violations.push(`${isoCode}: iconKey=${entry.iconKey}, expected prefix ${expected}`);
      }
    }
    expect(violations).toEqual([]);
  });
});
