import { describe, expect, it } from "vitest";
import { buildRunRecord } from "../../lib/admin/__fixtures__/runs";
import type { RunPipelineHealth } from "../../lib/admin/dataProvider";
import { deriveOperatorChecklist } from "./operatorChecklist";

const baseRun = buildRunRecord({
  id: "run_01",
  run_id: "run_01",
  source_id: "src_01",
  source_version_id: "sv_01",
  mode: "production",
  status: "running",
  started_at: "2026-04-07T10:00:00Z",
  completed_at: null,
  artifacts_count: 0,
  captured_resources_count: 0,
  created_at: "2026-04-07T09:59:00Z",
  updated_at: "2026-04-07T10:00:00Z",
});

const healthyPipeline: RunPipelineHealth = {
  run_id: "run_01",
  source_id: "src_01",
  source_version_id: "sv_01",
  mode: "production",
  run_status: "running",
  overall_status: "ok",
  stages: [],
  processing_status_event_count: 1,
  document_lifecycle_event_count: 1,
  // Required since #908: the judgement travels with the health payload rather
  // than being recomputed here. A fixture that omitted it would describe a
  // response the API cannot return.
  decision_support: {
    overall_summary: { code: "stages_healthy", text: "Pipeline stages are healthy." },
    why_it_matters: { code: "production_run", text: "" },
    what_is_blocked: { code: "no_stage_blocked", text: "No stage is blocked right now." },
    what_changed_recently: { code: "no_stage_updates", text: "" },
    what_happens_if_ignored: { code: "nothing_urgent", text: "" },
    blocked_stages: [],
    never_running_stages: [],
    next_actions: [],
  },
};

describe("deriveOperatorChecklist", () => {
  it("marks checklist items as ok for successful path", () => {
    const items = deriveOperatorChecklist({
      run: baseRun,
      health: healthyPipeline,
      readinessConfirmed: true,
      readinessBlockedCodes: [],
      verificationOpened: true,
    });

    expect(items.map((item) => item.state)).toEqual(["ok", "ok", "ok", "ok"]);
  });

  it("marks readiness as blocked when readiness codes exist", () => {
    const items = deriveOperatorChecklist({
      run: { ...baseRun, status: "pending", started_at: null },
      health: null,
      readinessConfirmed: false,
      readinessBlockedCodes: ["mode_compatible_with_version_status"],
      verificationOpened: false,
    });

    expect(items[0]).toMatchObject({
      key: "readiness",
      state: "blocked",
    });
    expect(items[2]).toMatchObject({
      key: "pipeline_visibility",
      state: "pending",
    });
    expect(items[0].detail).toContain("mode_compatible_with_version_status");
    expect(items[0].detail).toContain("approve the selected version before launch");
  });

  it("includes actionable fallback guidance for unknown readiness codes", () => {
    const items = deriveOperatorChecklist({
      run: { ...baseRun, status: "pending", started_at: null },
      health: null,
      readinessConfirmed: false,
      readinessBlockedCodes: ["custom_readiness_code"],
      verificationOpened: false,
    });

    expect(items[0]).toMatchObject({
      key: "readiness",
      state: "blocked",
    });
    expect(items[0].detail).toContain("custom_readiness_code");
    expect(items[0].detail).toContain("Review source/version configuration and retry.");
  });
});
