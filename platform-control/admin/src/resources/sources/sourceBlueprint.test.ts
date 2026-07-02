import { describe, expect, it } from "vitest";
import type {
  DeterministicHttpAcquisitionSpec,
  FedlexSparqlAcquisitionSpec,
  FirecrawlAcquisitionSpec,
  RisOgdAcquisitionSpec,
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
  spec:
    | FirecrawlAcquisitionSpec
    | DeterministicHttpAcquisitionSpec
    | RisOgdAcquisitionSpec
    | FedlexSparqlAcquisitionSpec,
): SourceBlueprintPreview => ({
  overlay_id: "ch",
  provider_template_id: "template-1",
  acquisition_spec: spec,
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
  { overlay_id: "ch", provider_template_id: "fedlex-default", provider: "fedlex_sparql" },
  { overlay_id: "ch", provider_template_id: "ch-http", provider: "deterministic_http" },
  { overlay_id: "at", provider_template_id: "ris-default", provider: "ris_ogd" },
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
      buildOverlayChoices([{ overlay_id: "xx", provider_template_id: "t", provider: "firecrawl" }]),
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
});
