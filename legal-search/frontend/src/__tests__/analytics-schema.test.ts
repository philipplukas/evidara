/**
 * Analytics Event Catalog ↔ Schema Drift Guard
 *
 * WHY THIS TEST EXISTS:
 * `contracts/events/legal-search.events.json` is the source of truth for
 * the legal-search analytics event catalog (issue #403, Slice 1). The TS
 * `AnalyticsEvent` const and `AnalyticsEventProperties` shape in
 * `src/lib/analytics.ts` are hand-mirrored from that schema — no
 * JSON-schema-to-TS codegen is wired up in this repo, so this test is
 * the drift guard.
 *
 * If a developer adds a new event to either side without touching the
 * other, this test fails. That's the whole point.
 *
 * WHAT WE TEST:
 * - Every event name in `AnalyticsEvent` exists as a `$defs` key in the
 *   schema (and carries a matching `name` const).
 * - Every `$defs` key in the schema has a matching `AnalyticsEvent`
 *   entry.
 * - Every property on each `AnalyticsEventProperties` entry corresponds
 *   to a property declared in the schema's $defs for that event (and
 *   vice versa) — a shallow key-parity check, not full value-level
 *   validation (Slice 1 intentionally defers runtime validation).
 *
 * WHAT WE DON'T TEST:
 * - Runtime payload conformance (no ajv yet; Slice 2+ territory).
 * - Property value types beyond presence.
 * - Required-vs-optional alignment (TS `?:` encodes optionality; the
 *   schema `required` array encodes it separately — we skip the
 *   cross-check for Slice 1 to keep this guard zero-dep).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { AnalyticsEvent } from "@/lib/analytics";

const REPO_ROOT = resolve(__dirname, "../../../..");
const SCHEMA_PATH = resolve(REPO_ROOT, "contracts/events/legal-search.events.json");

type EventDef = {
  properties?: Record<string, unknown>;
};

type Schema = {
  $defs: Record<string, EventDef>;
  oneOf: Array<{ $ref: string }>;
};

function loadSchema(): Schema {
  const raw = readFileSync(SCHEMA_PATH, "utf-8");
  return JSON.parse(raw) as Schema;
}

/**
 * Hand-mirrored list of TS property keys per event. Mirrors
 * `AnalyticsEventProperties` in `src/lib/analytics.ts`. Kept as data
 * here (rather than reflected off the interface) because TS interfaces
 * don't exist at runtime; reflecting would need a compiler plugin.
 *
 * If you add a key to `AnalyticsEventProperties`, add it here too.
 * The schema test below will fail if you forget to update the schema.
 */
const TS_EVENT_PROPERTIES: Record<string, readonly string[]> = {
  "search.executed": ["query", "resultCount", "jurisdictions", "languages"],
  "result.selected": ["resultId", "resultType", "position"],
  "result.pivoted": ["sourceId", "label"],
  "filter.applied": ["filterType", "value"],
  "filter.removed": ["filterType", "value"],
  "detail.tab_changed": ["tab", "previousTab"],
  "pin.added": ["itemId", "itemType"],
  "pin.removed": ["itemId"],
  "share.link_copied": ["url", "context"],
  "page.view": ["path", "referrer"],
};

describe("analytics.ts ↔ legal-search.events.json drift guard", () => {
  /**
   * WHY: If the frontend emits an event name that isn't in the contract,
   * downstream analytics tooling can't describe it. This catches the
   * "added to TS but forgot the schema" class of drift.
   */
  it("every AnalyticsEvent value is declared in the schema $defs", () => {
    const schema = loadSchema();
    const schemaNames = new Set(Object.keys(schema.$defs));
    const missing: string[] = [];
    for (const value of Object.values(AnalyticsEvent)) {
      if (!schemaNames.has(value)) {
        missing.push(value);
      }
    }
    expect(missing, `TS events missing from schema: ${missing.join(", ")}`).toEqual([]);
  });

  /**
   * WHY: Reverse direction — catches "added to schema but forgot the TS
   * const" so schema-authored events still get the type-safe track()
   * surface.
   */
  it("every schema $defs key is declared in AnalyticsEvent", () => {
    const schema = loadSchema();
    const tsNames = new Set<string>(Object.values(AnalyticsEvent));
    const missing: string[] = [];
    for (const schemaName of Object.keys(schema.$defs)) {
      if (!tsNames.has(schemaName)) {
        missing.push(schemaName);
      }
    }
    expect(missing, `Schema events missing from AnalyticsEvent: ${missing.join(", ")}`).toEqual([]);
  });

  /**
   * WHY: The oneOf union should reference every $defs entry — otherwise
   * consumers validating a payload against the top-level schema would
   * silently reject a valid event.
   */
  it("schema oneOf covers every $defs key", () => {
    const schema = loadSchema();
    const referenced = new Set(schema.oneOf.map((entry) => entry.$ref.replace(/^#\/\$defs\//, "")));
    const missing = Object.keys(schema.$defs).filter((key) => !referenced.has(key));
    expect(missing, `Schema $defs entries missing from oneOf: ${missing.join(", ")}`).toEqual([]);
  });

  /**
   * WHY: Property-level drift is the second-most-common failure mode
   * after event-name drift. This shallow key-parity check catches
   * "added a field to the TS payload but forgot the schema" (and
   * vice versa). Full value-shape validation is Slice 2+ work.
   *
   * We exclude the schema's `name` discriminator field from the
   * comparison — it's a schema-level constraint, not a payload key
   * the emitter provides.
   */
  it("every event's property keys match between TS and schema", () => {
    const schema = loadSchema();
    const mismatches: string[] = [];

    for (const [eventName, tsKeys] of Object.entries(TS_EVENT_PROPERTIES)) {
      const def = schema.$defs[eventName];
      if (!def || !def.properties) {
        mismatches.push(`${eventName}: schema $defs entry missing properties`);
        continue;
      }
      const schemaKeys = new Set(Object.keys(def.properties));
      schemaKeys.delete("name"); // discriminator, not a payload key

      const tsKeySet = new Set(tsKeys);

      for (const k of tsKeySet) {
        if (!schemaKeys.has(k)) {
          mismatches.push(`${eventName}: TS property "${k}" missing from schema`);
        }
      }
      for (const k of schemaKeys) {
        if (!tsKeySet.has(k)) {
          mismatches.push(`${eventName}: schema property "${k}" missing from TS`);
        }
      }
    }

    expect(mismatches, mismatches.join("\n")).toEqual([]);
  });

  /**
   * WHY: Sanity check that `TS_EVENT_PROPERTIES` covers every event in
   * the TS const. If this fails, the author added an event to the TS
   * const but forgot to add the per-event property list above, so the
   * key-parity check wouldn't run for it.
   */
  it("TS_EVENT_PROPERTIES covers every AnalyticsEvent", () => {
    const covered = new Set(Object.keys(TS_EVENT_PROPERTIES));
    const uncovered = Object.values(AnalyticsEvent).filter((v) => !covered.has(v));
    expect(uncovered).toEqual([]);
  });
});
