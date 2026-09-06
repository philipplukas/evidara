import { describe, expect, it } from "vitest";
import { buildRunTimeline } from "./runTimeline";

const at = (iso: string) => iso;

describe("buildRunTimeline", () => {
  it("interleaves the five stages into one ascending sequence", () => {
    const timeline = buildRunTimeline({
      documentLifecycle: [
        {
          event_id: "l1",
          event_type: "indexed",
          document_id: "doc_1",
          occurred_at: at("2026-09-01T10:04:00Z"),
        },
      ],
      providerJobs: [
        {
          provider_job_id: "j1",
          provider: "firecrawl",
          status: "completed",
          updated_at: at("2026-09-01T10:00:00Z"),
        },
      ],
      rawArtifacts: [{ artifact_id: "art_1", created_at: at("2026-09-01T10:02:00Z") }],
      capturedResources: [
        {
          captured_resource_id: "c1",
          title: "Hundegesetz",
          http_status: 200,
          fetched_at: at("2026-09-01T10:01:00Z"),
        },
      ],
      processingStatus: [
        {
          event_id: "p1",
          status: "canonical_ready",
          document_id: "doc_1",
          occurred_at: at("2026-09-01T10:03:00Z"),
        },
      ],
    });

    expect(timeline.map((e) => e.stage)).toEqual([
      "provider-job",
      "captured-resource",
      "raw-artifact",
      "processing-status",
      "document-lifecycle",
    ]);
  });

  it("prefixes ids with the stage so two stages cannot collide", () => {
    // `event_id` is the row id for BOTH processing status and lifecycle, so a
    // bare id would produce duplicate React keys across stages.
    const timeline = buildRunTimeline({
      processingStatus: [{ event_id: "e1", occurred_at: at("2026-09-01T10:00:00Z") }],
      documentLifecycle: [{ event_id: "e1", occurred_at: at("2026-09-01T10:01:00Z") }],
    });
    expect(new Set(timeline.map((e) => e.id)).size).toBe(2);
  });

  // Guard: dropping these would make the timeline quietly disagree with the
  // tables above it. Filter them out and this fails.
  it("keeps undated entries and sorts them last", () => {
    const timeline = buildRunTimeline({
      rawArtifacts: [
        { artifact_id: "undated" },
        { artifact_id: "dated", created_at: at("2026-09-01T10:00:00Z") },
      ],
    });
    expect(timeline).toHaveLength(2);
    expect(timeline.map((e) => e.summary)).toEqual(["Artifact dated", "Artifact undated"]);
    expect(timeline[1].occurredAt).toBeNull();
    expect(timeline[1].sortKey).toBeNull();
  });

  it("treats an unparseable timestamp as undated rather than sorting on NaN", () => {
    const timeline = buildRunTimeline({
      rawArtifacts: [
        { artifact_id: "bad", created_at: "not-a-date" },
        { artifact_id: "good", created_at: at("2026-09-01T10:00:00Z") },
      ],
    });
    expect(timeline[0].summary).toBe("Artifact good");
    expect(timeline[1].sortKey).toBeNull();
  });

  it("is stable for equal timestamps", () => {
    const stamp = at("2026-09-01T10:00:00Z");
    const timeline = buildRunTimeline({
      rawArtifacts: [
        { artifact_id: "a", created_at: stamp },
        { artifact_id: "b", created_at: stamp },
        { artifact_id: "c", created_at: stamp },
      ],
    });
    expect(timeline.map((e) => e.summary)).toEqual(["Artifact a", "Artifact b", "Artifact c"]);
  });

  describe("failure flagging", () => {
    it("flags a failed provider job and a failed processing update", () => {
      const timeline = buildRunTimeline({
        providerJobs: [
          { provider_job_id: "j", status: "failed", updated_at: at("2026-09-01T10:00:00Z") },
        ],
        processingStatus: [
          { event_id: "p", status: "failed", occurred_at: at("2026-09-01T10:01:00Z") },
        ],
      });
      expect(timeline.every((e) => e.isFailure)).toBe(true);
    });

    // Guard: `>= 400` alone would call a 3xx that never resolved a success.
    it.each([
      [200, false],
      [204, false],
      [301, true],
      [404, true],
      [500, true],
      [199, true],
    ])("http %s → isFailure %s", (status, expected) => {
      const [only] = buildRunTimeline({
        capturedResources: [
          {
            captured_resource_id: "c",
            http_status: status,
            fetched_at: at("2026-09-01T10:00:00Z"),
          },
        ],
      });
      expect(only.isFailure).toBe(expected);
    });

    it("does not flag a capture with no recorded status", () => {
      const [only] = buildRunTimeline({
        capturedResources: [{ captured_resource_id: "c", fetched_at: at("2026-09-01T10:00:00Z") }],
      });
      expect(only.isFailure).toBe(false);
      expect(only.detail).toBeNull();
    });
  });

  it("falls back through title → final_url → placeholder", () => {
    const build = (resource: Record<string, unknown>) =>
      buildRunTimeline({
        capturedResources: [
          { captured_resource_id: "c", fetched_at: at("2026-09-01T10:00:00Z"), ...resource },
        ],
        // biome-ignore lint/suspicious/noExplicitAny: structural test input
      } as any)[0].summary;

    expect(build({ title: "T", final_url: "https://x" })).toBe("T");
    expect(build({ title: "   ", final_url: "https://x" })).toBe("https://x");
    expect(build({})).toBe("Untitled resource");
  });

  it("returns [] when every stage is absent, null or empty", () => {
    expect(buildRunTimeline({})).toEqual([]);
    expect(
      buildRunTimeline({
        providerJobs: null,
        capturedResources: [],
        rawArtifacts: undefined,
      }),
    ).toEqual([]);
  });
});
