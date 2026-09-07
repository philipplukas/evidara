/**
 * The `acquisition_spec` of a source version, arranged for reading.
 *
 * WHY THIS EXISTS. The complete spec has always been on the wire —
 * `SourceVersionResponse.acquisition_spec` — and the panel rendered it in full in
 * exactly one place: the create wizard, before the source exists. Once a version
 * existed, the versions table showed `summarizeAcquisitionSpec` instead, which is
 * lossy by construction:
 *
 *   - it drops every `BASE_SPEC_FIELDS` entry — `tenant_id`, `corpus_id`,
 *     `scope_type`, `source_origin_kind`, `trust_tier`, `language_codes` — which
 *     are the fields ADR-0030 and the compliance policy actually gate on; and
 *   - it has real renderers for four of eleven providers, so the rest fall through
 *     to a generic listing (that same base-field exclusion applies there too).
 *
 * So an operator could see the whole configuration at the moment it did not exist
 * yet, and a filtered view of it forever after. That is backwards: the moment you
 * most need to know what a run will do is when it is about to run.
 *
 * The summary is still the right thing in a table cell. This is the seam that
 * makes the truth reachable from beside it.
 *
 * No React here — data in, data out — so the partitioning is unit-testable without
 * rendering anything.
 */
import type { AcquisitionSpec } from "../../lib/admin/dataProvider";
import { BASE_SPEC_FIELDS } from "./sourceVersionForm";

export type SpecEntry = { key: string; value: unknown };

export type PartitionedSpec = {
  /** The provider, pulled out because it decides how everything else reads. */
  provider: string;
  /**
   * Tenancy, corpus, scope and trust. Constant-looking and therefore easy to
   * treat as boilerplate — but `corpus_id` is what a document is written into and
   * `trust_tier` is what downstream ranking believes, so a wrong one here is a
   * silent, corpus-wide defect. The summary shows none of them.
   */
  identity: SpecEntry[];
  /** Everything the provider itself acts on. */
  providerConfig: SpecEntry[];
};

const IDENTITY_KEYS: ReadonlySet<string> = new Set(BASE_SPEC_FIELDS);

/**
 * Split a spec into provider / identity / provider-config.
 *
 * Nothing is discarded: `identity` and `providerConfig` together account for every
 * key except `provider`. `partitionCoversEverySpecKey` is the test that keeps that
 * true, because a partition that silently drops a key would reintroduce exactly
 * the defect this module exists to fix.
 */
export function partitionAcquisitionSpec(spec: AcquisitionSpec): PartitionedSpec {
  const entries = Object.entries(spec as Record<string, unknown>);
  const identity: SpecEntry[] = [];
  const providerConfig: SpecEntry[] = [];

  for (const [key, value] of entries) {
    if (key === "provider") continue;
    (IDENTITY_KEYS.has(key) ? identity : providerConfig).push({ key, value });
  }

  // Stable, readable order: identity follows the declared field order rather than
  // whatever order the server serialised.
  const declared = [...BASE_SPEC_FIELDS] as string[];
  identity.sort((a, b) => declared.indexOf(a.key) - declared.indexOf(b.key));
  providerConfig.sort((a, b) => a.key.localeCompare(b.key));

  return {
    provider: String((spec as Record<string, unknown>).provider ?? "unknown"),
    identity,
    providerConfig,
  };
}

/** Every key the partition accounts for, `provider` included. */
export function partitionedKeys(partitioned: PartitionedSpec): string[] {
  return [
    "provider",
    ...partitioned.identity.map((e) => e.key),
    ...partitioned.providerConfig.map((e) => e.key),
  ];
}

/**
 * Render one value the way an operator reads it, not the way JSON prints it.
 *
 * `null` and `undefined` are shown as "not set" rather than omitted: a field that
 * exists and is empty is a different fact from a field that is absent, and
 * collapsing the two is how "declared with no producer" hides.
 */
export function formatSpecEntryValue(value: unknown): string {
  if (value === null || value === undefined) return "not set";
  if (Array.isArray(value)) return value.length === 0 ? "empty list" : value.map(String).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}
