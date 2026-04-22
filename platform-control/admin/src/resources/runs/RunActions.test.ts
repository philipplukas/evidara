import { describe, expect, it } from "vitest";
import type { RunRecord } from "../../lib/admin/dataProvider";
import { canPromoteRunToProduction } from "./RunActions";

const completedPreviewRun: RunRecord = {
  id: "run-preview",
  run_id: "run-preview",
  source_id: "source-1",
  source_version_id: "version-1",
  mode: "preview",
  status: "completed",
  started_at: "2026-04-15T09:00:00Z",
  completed_at: "2026-04-15T09:30:00Z",
  artifacts_count: 4,
  captured_resources_count: 12,
  failure_reason: null,
  created_at: "2026-04-15T08:55:00Z",
  updated_at: "2026-04-15T09:30:00Z",
};

describe("run promotion actions", () => {
  it("allows promotion only for completed preview runs", () => {
    expect(canPromoteRunToProduction(completedPreviewRun)).toBe(true);
    expect(
      canPromoteRunToProduction({
        ...completedPreviewRun,
        mode: "production",
      }),
    ).toBe(false);
    expect(
      canPromoteRunToProduction({
        ...completedPreviewRun,
        status: "running",
        completed_at: null,
      }),
    ).toBe(false);
  });
});
