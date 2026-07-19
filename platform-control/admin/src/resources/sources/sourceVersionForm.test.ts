import { describe, expect, it } from "vitest";
import type { AcquisitionSpec, SourceVersionRecord } from "../../lib/admin/dataProvider";
import {
  describeSourceVersionStatus,
  emptyFormState,
  explainUnavailableVersionAction,
  type SourceVersionAction,
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

/**
 * A real `canton_http` spec, as the API serves it.
 *
 * `canton_http` is one of the seven providers the live API serves and this form
 * has no widgets for. The admin's `AcquisitionSpec` union models only the four
 * it can edit, hence the cast — the wire really does carry this shape (#614).
 */
const CANTON_HTTP_SPEC = {
  provider: "canton_http",
  canton_code: "CH-ZH",
  seed_url: "https://www.zh.ch/de/politik-staat/gesetze-beschluesse.html",
  seed_urls: [],
  tenant_id: "tenant_public",
  corpus_id: "corpus_public_ch_zh_legislation",
  scope_type: "global_public",
  source_origin_kind: "official_primary",
  trust_tier: "authoritative",
  language_codes: ["de"],
  document_type_hint: "legislation",
  request_timeout_seconds: 30,
  user_agent: null,
  max_content_bytes: 2_000_000,
} as unknown as AcquisitionSpec;

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

describe("explainUnavailableVersionAction", () => {
  it("states why every action is blocked on an approved version", () => {
    // The live repro (#674): an approved version rendered Edit / Approve /
    // Reject as three greyed buttons with no stated reason.
    expect(explainUnavailableVersionAction("edit", "approved")).toContain("immutable");
    expect(explainUnavailableVersionAction("approve", "approved")).toContain("terminal");
    expect(explainUnavailableVersionAction("reject", "approved")).toContain("terminal");
  });

  it("returns null for the actions an approved version can still take", () => {
    expect(explainUnavailableVersionAction("preview", "approved")).toBeNull();
    expect(explainUnavailableVersionAction("production", "approved")).toBeNull();
  });

  it("leaves a draft's review actions available and explains the production block", () => {
    expect(explainUnavailableVersionAction("edit", "draft")).toBeNull();
    expect(explainUnavailableVersionAction("approve", "draft")).toBeNull();
    expect(explainUnavailableVersionAction("reject", "draft")).toBeNull();
    expect(explainUnavailableVersionAction("preview", "draft")).toBeNull();
    expect(explainUnavailableVersionAction("production", "draft")).toContain("approved version");
  });

  it("explains the rejected and superseded dead ends", () => {
    expect(explainUnavailableVersionAction("edit", "rejected")).toBeNull();
    expect(explainUnavailableVersionAction("preview", "rejected")).toContain("blocked");
    expect(explainUnavailableVersionAction("approve", "rejected")).toContain("already rejected");
    expect(explainUnavailableVersionAction("edit", "superseded")).toContain("read-only");
    expect(explainUnavailableVersionAction("preview", "superseded")).toContain("read-only");
  });

  it("preserves the availability matrix the row's ad-hoc booleans encoded", () => {
    // This helper replaced four inline booleans in `SourceVersionsSection`
    // (`canEdit` / `canReview` / `canPreview` / `canProduction`). Adding the
    // explanation must not change *which* buttons are disabled, so the whole
    // 5x5 matrix is pinned against the behaviour those booleans produced.
    const available: Record<SourceVersionRecord["status"], SourceVersionAction[]> = {
      draft: ["edit", "preview", "approve", "reject"],
      pending_approval: ["preview", "approve", "reject"],
      approved: ["preview", "production"],
      rejected: ["edit"],
      superseded: [],
    };
    const allActions: SourceVersionAction[] = [
      "edit",
      "preview",
      "production",
      "approve",
      "reject",
    ];

    for (const [status, expected] of Object.entries(available)) {
      const actual = allActions.filter(
        (action) =>
          explainUnavailableVersionAction(action, status as SourceVersionRecord["status"]) === null,
      );
      expect({ status, actual }).toEqual({
        status,
        actual: allActions.filter((a) => expected.includes(a)),
      });
    }
  });

  it("keeps a pending-approval version reviewable but not editable", () => {
    expect(explainUnavailableVersionAction("approve", "pending_approval")).toBeNull();
    expect(explainUnavailableVersionAction("reject", "pending_approval")).toBeNull();
    expect(explainUnavailableVersionAction("edit", "pending_approval")).toContain("review");
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

  it("summarizes an unknown provider from its own fields, not firecrawl's", () => {
    const lines = summarizeAcquisitionSpec(CANTON_HTTP_SPEC);

    expect(lines[0]).toBe("provider: canton_http");
    expect(lines).toContain("canton_code: CH-ZH");
    // The firecrawl fallthrough used to print these over a spec that has none
    // of them (`admin-04-canton-http-show.png` in #614).
    expect(lines).not.toContain("mode: undefined");
    expect(lines).not.toContain("limit: undefined");
  });
});

/**
 * The server REPLACES `acquisition_spec` wholesale
 * (`source_service.update_source_version`), so whatever `toAcquisitionSpec`
 * omits resets to its schema default. `toFormState` -> `toAcquisitionSpec` must
 * therefore be lossless for every field, including the ones the dialog does not
 * render (#614).
 */
describe("acquisition-spec round-trip (#614)", () => {
  it("preserves the BaseAcquisitionSpec fields the dialog never renders", () => {
    const spec: AcquisitionSpec = {
      provider: "firecrawl",
      seed_url: "https://www.fedlex.admin.ch/eli/cc/1999/404",
      seed_urls: [],
      mode: "crawl",
      include_paths: [],
      exclude_paths: [],
      limit: 20,
      max_discovery_depth: 2,
      scrape_formats: ["markdown", "html"],
      zero_data_retention: false,
      // None of the below has a widget in the dialog. Renaming a version label
      // reset corpus_id -> corpus_public_default, language_codes -> [] and
      // document_type_hint -> null.
      tenant_id: "tenant_public",
      corpus_id: "corpus_public_ch_fedlex_constitution",
      scope_type: "global_public",
      source_origin_kind: "official_primary",
      trust_tier: "authoritative",
      language_codes: ["de"],
      document_type_hint: "legislation",
      request_timeout_seconds: 30,
      user_agent: null,
      max_content_bytes: 2_000_000,
    };

    const form = toFormState(baseVersion({ acquisition_spec: spec }));

    // Renaming the label is the exact edit that corrupted the spec.
    expect(toAcquisitionSpec({ ...form, version_label: "v2" })).toEqual(spec);
  });

  it("keeps an unknown provider's spec instead of rewriting it as firecrawl", () => {
    const form = toFormState(baseVersion({ acquisition_spec: CANTON_HTTP_SPEC }));

    // Opening Edit and saving unchanged turned provider canton_http ->
    // firecrawl and canton_code CH-ZH -> null. canton_code is the field that
    // defines what the source is.
    expect(toAcquisitionSpec(form)).toEqual(CANTON_HTTP_SPEC);
  });

  it("round-trips a fedlex_sparql spec without duplicating seed_url into seed_urls", () => {
    const spec: AcquisitionSpec = {
      provider: "fedlex_sparql",
      seed_url: "https://fedlex.data.admin.ch/eli/cc/1999/404",
      seed_urls: ["https://fedlex.data.admin.ch/eli/cc/2000/1"],
      sparql_endpoint: "https://fedlex.data.admin.ch/sparqlendpoint",
      preferred_languages: ["de", "fr"],
      query_mode: "work_to_expression",
      max_expressions: 3,
      corpus_id: "corpus_public_ch_fedlex_constitution",
      language_codes: ["de"],
    };

    const form = toFormState(baseVersion({ acquisition_spec: spec }));

    expect(toAcquisitionSpec(form)).toEqual(spec);
  });

  it("carries base fields across a provider switch but drops the old provider's fields", () => {
    const form = toFormState(
      baseVersion({
        acquisition_spec: {
          provider: "firecrawl",
          seed_url: "https://example.test",
          seed_urls: [],
          mode: "crawl",
          include_paths: ["/law"],
          exclude_paths: [],
          limit: 20,
          max_discovery_depth: 2,
          scrape_formats: ["markdown"],
          zero_data_retention: false,
          corpus_id: "corpus_public_ch_fedlex_constitution",
          language_codes: ["de"],
        },
      }),
    );

    const spec = toAcquisitionSpec({ ...form, provider: "deterministic_http" });

    // Base fields are provider-independent, so they survive the switch...
    expect(spec).toMatchObject({
      provider: "deterministic_http",
      seed_url: "https://example.test",
      corpus_id: "corpus_public_ch_fedlex_constitution",
      language_codes: ["de"],
    });
    // ...but firecrawl's own fields are not valid on deterministic_http, and
    // the server's spec models are `extra="forbid"`.
    expect(spec).not.toHaveProperty("mode");
    expect(spec).not.toHaveProperty("include_paths");
    expect(spec).not.toHaveProperty("limit");
  });
});
