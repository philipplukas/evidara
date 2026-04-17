import { describe, expect, it } from "vitest";
import type { SourceVersionRecord } from "../../lib/admin/dataProvider";
import {
  describeSourceVersionStatus,
  summarizeSourceVersionLifecycle,
} from "./SourceVersionsSection";

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
