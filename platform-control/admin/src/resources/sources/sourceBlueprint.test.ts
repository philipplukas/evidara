import { describe, expect, it } from "vitest";
import { buildAcquisitionSpec } from "../../lib/admin/__fixtures__/acquisitionSpecs";
import type {
  AcquisitionSpec,
  SourceBlueprintPreview,
  SourceBlueprintTemplate,
} from "../../lib/admin/dataProvider";
import {
  buildOverlayChoices,
  buildTemplateChoicesByOverlay,
  OVERLAY_NAMES,
  summarizePreview,
} from "./sourceBlueprint";

const previewFor = (
  spec: { provider: AcquisitionSpec["provider"] } & Record<string, unknown>,
): SourceBlueprintPreview => ({
  overlay_id: "ch",
  provider_template_id: "template-1",
  acquisition_spec: buildAcquisitionSpec(spec),
  enabled: true,
  live_ready: true,
  launchable: true,
  notes: [],
});

/** Template fixture with the two-key lock open by default (launchable). */
const mkTemplate = (
  overrides: Partial<SourceBlueprintTemplate> &
    Pick<SourceBlueprintTemplate, "overlay_id" | "provider_template_id" | "provider">,
): SourceBlueprintTemplate => ({
  enabled: true,
  live_ready: true,
  launchable: true,
  notes: [],
  // Config-key provenance (#668): the API always emits these, so a fixture
  // without them is a shape the server never returns.
  default_enabled: true,
  source: "default",
  note: null,
  updated_by: null,
  updated_at: null,
  ...overrides,
});

describe("summarizePreview", () => {
  it("summarizes a ris_ogd spec", () => {
    const lines = summarizePreview(
      previewFor({
        provider: "ris_ogd",
        base_url: "https://ris.example/api",
        applikation: "Bundesnormen",
        preferred_formats: ["xml", "html"],
        page_size: 50,
        max_pages: 10,
      }),
    );

    expect(lines).toContain("Provider: ris_ogd");
    expect(lines).toContain("Base URL: https://ris.example/api");
    expect(lines).toContain("Applikation: Bundesnormen");
    expect(lines).toContain("Preferred formats: xml, html");
    expect(lines).toContain("Page size/max pages: 50 / 10");
  });

  it("summarizes a fedlex_sparql spec and merges seed_url with seed_urls", () => {
    const lines = summarizePreview(
      previewFor({
        provider: "fedlex_sparql",
        seed_url: "https://fedlex/eli/work-a",
        seed_urls: ["https://fedlex/eli/work-b"],
        sparql_endpoint: "https://fedlex/sparql",
        preferred_languages: ["de", "fr"],
        query_mode: "work_to_expression",
        max_expressions: 25,
      }),
    );

    expect(lines).toContain("Provider: fedlex_sparql");
    expect(lines).toContain("Seed work URIs: https://fedlex/eli/work-a, https://fedlex/eli/work-b");
    expect(lines).toContain("SPARQL endpoint: https://fedlex/sparql");
    expect(lines).toContain("Preferred languages: de, fr");
    expect(lines).toContain("Query mode/max expressions: work_to_expression / 25");
  });

  it("summarizes a deterministic_http spec", () => {
    const lines = summarizePreview(
      previewFor({
        provider: "deterministic_http",
        seed_url: null,
        seed_urls: ["https://static/a", "https://static/b"],
        tenant_id: "tenant-1",
        corpus_id: "corpus-1",
      }),
    );

    expect(lines).toContain("Provider: deterministic_http");
    expect(lines).toContain("Seeds: https://static/a, https://static/b");
    expect(lines).toContain("Tenant/corpus: tenant-1 / corpus-1");
  });

  /**
   * #737 — a provider with no dedicated branch gets a generic summary built
   * from fields every spec has. It used to fall through to the *firecrawl*
   * branch, so `canton_http` was described by a spec it does not have: three
   * lines of `n/a` for mode, limit/depth and formats, and no `canton_code`.
   * The four-provider union made that unrepresentable-and-therefore-untestable;
   * the contract's eleven-provider union makes it plain.
   */
  it("summarizes a provider without a dedicated branch from its shared fields", () => {
    const lines = summarizePreview(
      previewFor({
        provider: "canton_http",
        canton_code: "CH-ZH",
        seed_url: "https://www.zh.ch/gesetzessammlung",
        seed_urls: [],
        tenant_id: "tenant_public",
        corpus_id: "corpus_public_ch_zh_legislation",
      }),
    );

    expect(lines).toContain("Provider: canton_http");
    expect(lines).toContain("Seeds: https://www.zh.ch/gesetzessammlung");
    expect(lines).toContain("Tenant/corpus: tenant_public / corpus_public_ch_zh_legislation");
    // The firecrawl fallthrough used to emit these over a spec that has none.
    expect(lines.join("\n")).not.toContain("Mode:");
    expect(lines.join("\n")).not.toContain("Limit/depth:");
    expect(lines.join("\n")).not.toContain("Formats:");
  });

  it("falls through to a firecrawl-style summary for the firecrawl provider", () => {
    const lines = summarizePreview(
      previewFor({
        provider: "firecrawl",
        seed_url: "https://crawl/root",
        seed_urls: [],
        mode: "crawl",
        include_paths: [],
        exclude_paths: [],
        limit: 100,
        max_discovery_depth: 3,
        scrape_formats: ["markdown"],
        zero_data_retention: false,
      }),
    );

    expect(lines).toContain("Provider: firecrawl");
    expect(lines).toContain("Mode: crawl");
    expect(lines).toContain("Seeds: https://crawl/root");
    expect(lines).toContain("Limit/depth: 100 / 3");
    expect(lines).toContain("Formats: markdown");
  });

  it("renders n/a for a spec with no mode instead of the literal 'undefined'", () => {
    // Live repro: picking overlay `ch` / template `canton_http_zh` in the create
    // wizard rendered "Mode: undefined" to the operator, because the canton_http
    // spec carries no `mode`. Match the "n/a" convention the sibling lines use.
    const lines = summarizePreview(
      previewFor({
        provider: "firecrawl",
        seed_url: "https://zh.ch/gesetzessammlung",
        seed_urls: [],
        mode: undefined as unknown as "crawl",
        include_paths: [],
        exclude_paths: [],
        limit: 10,
        max_discovery_depth: 1,
        scrape_formats: [],
        zero_data_retention: false,
      }),
    );

    expect(lines).toContain("Mode: n/a");
    expect(lines.join("\n")).not.toContain("undefined");
  });

  it("renders n/a when a firecrawl spec has no seeds", () => {
    const lines = summarizePreview(
      previewFor({
        provider: "firecrawl",
        seed_url: null,
        seed_urls: [],
        mode: "batch_scrape",
        include_paths: [],
        exclude_paths: [],
        limit: 10,
        max_discovery_depth: 1,
        scrape_formats: [],
        zero_data_retention: true,
      }),
    );

    expect(lines).toContain("Seeds: n/a");
    expect(lines).toContain("Formats: n/a");
  });
});

const templates: SourceBlueprintTemplate[] = [
  mkTemplate({
    overlay_id: "ch",
    provider_template_id: "fedlex-default",
    provider: "fedlex_sparql",
  }),
  mkTemplate({ overlay_id: "ch", provider_template_id: "ch-http", provider: "deterministic_http" }),
  mkTemplate({ overlay_id: "at", provider_template_id: "ris-default", provider: "ris_ogd" }),
];

describe("buildOverlayChoices", () => {
  it("returns distinct overlays in first-seen order with friendly labels", () => {
    expect(buildOverlayChoices(templates)).toEqual([
      { id: "ch", name: OVERLAY_NAMES.ch },
      { id: "at", name: OVERLAY_NAMES.at },
    ]);
  });

  it("upper-cases unknown overlay ids", () => {
    expect(
      buildOverlayChoices([
        mkTemplate({ overlay_id: "xx", provider_template_id: "t", provider: "firecrawl" }),
      ]),
    ).toEqual([{ id: "xx", name: "XX" }]);
  });
});

describe("buildTemplateChoicesByOverlay", () => {
  it("groups provider-template choices by overlay id with `id (provider)` labels", () => {
    expect(buildTemplateChoicesByOverlay(templates)).toEqual({
      ch: [
        { id: "fedlex-default", name: "fedlex-default (fedlex_sparql)" },
        { id: "ch-http", name: "ch-http (deterministic_http)" },
      ],
      at: [{ id: "ris-default", name: "ris-default (ris_ogd)" }],
    });
  });

  it("marks an inert (non-launchable) template at selection time so it isn't mistaken for live", () => {
    const grouped = buildTemplateChoicesByOverlay([
      mkTemplate({
        overlay_id: "ch",
        provider_template_id: "canton_http_zh",
        provider: "deterministic_http",
        enabled: false,
        live_ready: false,
        launchable: false,
        notes: ["Config key closed", "Code key closed"],
      }),
    ]);

    expect(grouped.ch).toEqual([
      { id: "canton_http_zh", name: "canton_http_zh (deterministic_http) · inert (locked)" },
    ]);
  });
});
