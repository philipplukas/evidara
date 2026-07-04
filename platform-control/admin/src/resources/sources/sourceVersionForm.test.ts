import { describe, expect, it } from "vitest";
import type { SourceVersionRecord } from "../../lib/admin/dataProvider";
import {
  describeSourceVersionStatus,
  emptyFormState,
  summarizeAcquisitionSpec,
  summarizeSourceVersionLifecycle,
  toAcquisitionSpec,
  toFormState,
} from "./sourceVersionForm";

const baseVersion = (overrides: Partial<SourceVersionRecord>): SourceVersionRecord => ({
  id: overrides.source_version_id ?? "sv-default",
  source_version_id: overrides.source_version_id ?? "sv-default",
  source_id: overrides.source_id ?? "source-1",
  extractor_profile_id: overrides.extractor_profile_id ?? null,
  version_label: overrides.version_label ?? "v1",
  status: overrides.status ?? "draft",
  acquisition_spec: overrides.acquisition_spec ?? {
    provider: "firecrawl",
    seed_url: null,
    seed_urls: [],
    mode: "crawl",
    include_paths: [],
    exclude_paths: [],
    limit: 20,
    max_discovery_depth: 2,
    scrape_formats: [],
    zero_data_retention: false,
  },
  created_at: overrides.created_at ?? "2026-04-10T10:00:00Z",
  updated_at: overrides.updated_at ?? "2026-04-10T10:00:00Z",
});

describe("SourceVersionsSection helpers", () => {
  it("summarizes lifecycle counts and the next operator action", () => {
    const summary = summarizeSourceVersionLifecycle([
      baseVersion({ source_version_id: "sv-draft", status: "draft" }),
      baseVersion({ source_version_id: "sv-pending", status: "pending_approval" }),
      baseVersion({ source_version_id: "sv-approved", status: "approved" }),
      baseVersion({ source_version_id: "sv-rejected", status: "rejected" }),
    ]);

    expect(summary.total).toBe(4);
    expect(summary.counts).toEqual({
      draft: 1,
      pending_approval: 1,
      approved: 1,
      rejected: 1,
      superseded: 0,
    });
    expect(summary.attentionCount).toBe(3);
    expect(summary.nextAction).toBe("Finish the draft version.");
    expect(summary.latestVersion?.source_version_id).toBe("sv-draft");
  });

  it("describes an empty lifecycle as a create-first-version task", () => {
    const summary = summarizeSourceVersionLifecycle([]);

    expect(summary.total).toBe(0);
    expect(summary.attentionCount).toBe(0);
    expect(summary.nextAction).toBe("Create the first source version.");
    expect(summary.nextActionDetail).toContain("draft");
    expect(summary.latestVersion).toBeNull();
  });

  it("maps status values to the expected operator labels", () => {
    expect(describeSourceVersionStatus("approved")).toMatchObject({
      label: "Approved",
      attention: false,
    });
    expect(describeSourceVersionStatus("rejected")).toMatchObject({
      label: "Rejected",
      attention: true,
    });
  });
});

describe("acquisition-spec form helpers", () => {
  it("builds a firecrawl acquisition spec from the empty form defaults", () => {
    const spec = toAcquisitionSpec(emptyFormState());

    expect(spec).toMatchObject({
      provider: "firecrawl",
      mode: "crawl",
      limit: 20,
      max_discovery_depth: 2,
      scrape_formats: ["markdown", "html"],
      zero_data_retention: false,
    });
  });

  it("parses list fields and coerces integers for the ris_ogd provider", () => {
    const spec = toAcquisitionSpec({
      ...emptyFormState(),
      provider: "ris_ogd",
      base_url: "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht",
      applikation: "  ",
      preferred_formats_text: "Xml, Html",
      page_size: "25",
      max_pages: "40",
    });

    expect(spec).toMatchObject({
      provider: "ris_ogd",
      base_url: "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht",
      applikation: null,
      preferred_formats: ["Xml", "Html"],
      page_size: 25,
      max_pages: 40,
    });
  });

  it("throws a descriptive error for out-of-range integer fields", () => {
    expect(() =>
      toAcquisitionSpec({ ...emptyFormState(), provider: "firecrawl", limit: "999" }),
    ).toThrow("Limit must be between 1 and 500.");
  });

  it("round-trips a fedlex_sparql spec through the form state and back", () => {
    const version: SourceVersionRecord = baseVersion({
      status: "approved",
      acquisition_spec: {
        provider: "fedlex_sparql",
        seed_url: "https://fedlex.data.admin.ch/eli/cc/1999/404",
        seed_urls: ["https://fedlex.data.admin.ch/eli/cc/2000/1"],
        sparql_endpoint: "https://fedlex.data.admin.ch/sparqlendpoint",
        preferred_languages: ["de", "fr"],
        query_mode: "work_to_expression",
        max_expressions: 3,
      },
    });

    const form = toFormState(version);
    expect(form.provider).toBe("fedlex_sparql");
    expect(form.max_expressions).toBe("3");

    const spec = toAcquisitionSpec(form);
    expect(spec).toMatchObject({
      provider: "fedlex_sparql",
      seed_url: "https://fedlex.data.admin.ch/eli/cc/1999/404",
      sparql_endpoint: "https://fedlex.data.admin.ch/sparqlendpoint",
      preferred_languages: ["de", "fr"],
      query_mode: "work_to_expression",
      max_expressions: 3,
    });
  });

  it("summarizes an acquisition spec into operator-facing lines", () => {
    const lines = summarizeAcquisitionSpec({
      provider: "firecrawl",
      seed_url: "https://example.test",
      seed_urls: [],
      mode: "crawl",
      include_paths: [],
      exclude_paths: [],
      limit: 20,
      max_discovery_depth: 2,
      scrape_formats: ["markdown"],
      zero_data_retention: false,
    });

    expect(lines[0]).toBe("provider: firecrawl");
    expect(lines).toContain("seeds: https://example.test");
    expect(lines).toContain("zero retention: no");
  });
});
