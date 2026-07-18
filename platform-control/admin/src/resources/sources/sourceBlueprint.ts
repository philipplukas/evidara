/**
 * Shared source-create blueprint helpers.
 *
 * The source-create wizard turns a country overlay + provider template into
 * a server-expanded `acquisition_spec` (previewed via
 * `controlPlaneActions.previewSourceBlueprint`). The pure, framework-agnostic
 * pieces of that flow live here — separated from the Tailwind
 * `SourceCreate.tsx` wizard so they can be unit-tested in isolation:
 *
 *   - `OVERLAY_NAMES` — overlay-id -> operator-facing label.
 *   - `summarizePreview` — provider-specific one-line summary of an expanded
 *     acquisition spec (the human-readable preview lines).
 *   - `buildOverlayChoices` / `buildTemplateChoicesByOverlay` — derive the
 *     overlay `<Select>` choices and the per-overlay provider-template
 *     choices from the flat blueprint-template list.
 *
 * No React, no MUI, no Tailwind — just data in, data out.
 */
import type {
  FedlexSparqlAcquisitionSpec,
  SourceBlueprintPreview,
  SourceBlueprintTemplate,
} from "../../lib/admin/dataProvider";

/** Choice shape shared with the `<Select>` primitive (`SelectChoice`). */
export type BlueprintChoice = {
  id: string;
  name: string;
};

export const OVERLAY_NAMES: Record<string, string> = {
  at: "Austria (AT)",
  de: "Germany (DE)",
  ch: "Switzerland (CH)",
  fr: "France (FR)",
  it: "Italy (IT)",
};

/**
 * Provider-specific, human-readable summary of an expanded acquisition spec.
 * Returns one display line per salient field; the caller renders them as a
 * list. Falls through to a generic Firecrawl-style summary for any provider
 * that isn't specifically special-cased.
 */
export const summarizePreview = (preview: SourceBlueprintPreview): string[] => {
  const spec = preview.acquisition_spec;
  if (spec.provider === "ris_ogd") {
    return [
      `Provider: ${spec.provider}`,
      `Base URL: ${spec.base_url}`,
      `Applikation: ${spec.applikation ?? "all"}`,
      `Preferred formats: ${(spec.preferred_formats ?? []).join(", ") || "n/a"}`,
      `Page size/max pages: ${spec.page_size ?? "n/a"} / ${spec.max_pages ?? "n/a"}`,
    ];
  }
  if (spec.provider === "fedlex_sparql") {
    const fedlex = spec as FedlexSparqlAcquisitionSpec;
    const seeds = fedlex.seed_url
      ? [fedlex.seed_url, ...(fedlex.seed_urls ?? [])]
      : (fedlex.seed_urls ?? []);
    return [
      `Provider: ${fedlex.provider}`,
      `Seed work URIs: ${seeds.join(", ") || "n/a"}`,
      `SPARQL endpoint: ${fedlex.sparql_endpoint ?? "n/a"}`,
      `Preferred languages: ${(fedlex.preferred_languages ?? []).join(", ") || "n/a"}`,
      `Query mode/max expressions: ${fedlex.query_mode ?? "n/a"} / ${fedlex.max_expressions ?? "n/a"}`,
    ];
  }
  if (spec.provider === "deterministic_http") {
    const seeds = spec.seed_url
      ? [spec.seed_url, ...(spec.seed_urls ?? [])]
      : (spec.seed_urls ?? []);
    return [
      `Provider: ${spec.provider}`,
      `Seeds: ${seeds.join(", ") || "n/a"}`,
      `Tenant/corpus: ${spec.tenant_id ?? "n/a"} / ${spec.corpus_id ?? "n/a"}`,
    ];
  }
  const seeds = spec.seed_url ? [spec.seed_url, ...(spec.seed_urls ?? [])] : (spec.seed_urls ?? []);
  return [
    `Provider: ${spec.provider}`,
    `Mode: ${spec.mode}`,
    `Seeds: ${seeds.join(", ") || "n/a"}`,
    `Limit/depth: ${spec.limit ?? "n/a"} / ${spec.max_discovery_depth ?? "n/a"}`,
    `Formats: ${(spec.scrape_formats ?? []).join(", ") || "n/a"}`,
  ];
};

/** Distinct overlay choices, in first-seen order, labelled via `OVERLAY_NAMES`. */
export const buildOverlayChoices = (templates: SourceBlueprintTemplate[]): BlueprintChoice[] =>
  Array.from(new Set(templates.map((template) => template.overlay_id))).map((overlayId) => ({
    id: overlayId,
    name: OVERLAY_NAMES[overlayId] ?? overlayId.toUpperCase(),
  }));

/**
 * Provider-template choices grouped by overlay id, labelled `id (provider)`.
 *
 * Inert templates (either ADR-0030 key still closed — not `launchable`) are
 * marked at selection time so an operator sees the lock *before* investing in a
 * source, instead of walking four green steps into a 400 (#634). The panel isn't
 * wrong today; it simply had nothing to render — the API now reports the lock.
 */
export const buildTemplateChoicesByOverlay = (
  templates: SourceBlueprintTemplate[],
): Record<string, BlueprintChoice[]> => {
  const grouped: Record<string, BlueprintChoice[]> = {};
  for (const template of templates) {
    const list = grouped[template.overlay_id] ?? [];
    const marker = template.launchable ? "" : " · inert (locked)";
    list.push({
      id: template.provider_template_id,
      name: `${template.provider_template_id} (${template.provider})${marker}`,
    });
    grouped[template.overlay_id] = list;
  }
  return grouped;
};
