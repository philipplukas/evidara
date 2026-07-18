import { describe, expect, it } from "vitest";
import type {
  RunPipelineHealth,
  RunPipelineHealthStage,
  RunRecord,
} from "../../lib/admin/dataProvider";
import { buildRunDecisionSupport } from "./RunShow";
import { buildPipelineDecisionSupport } from "./run-decision-support";

const baseRun: RunRecord = {
  id: "run-123",
  run_id: "run-123",
  source_id: "source-1",
  source_version_id: "version-1",
  mode: "preview",
  status: "running",
  started_at: "2026-04-10T09:00:00Z",
  completed_at: null,
  artifacts_count: 3,
  captured_resources_count: 12,
  failure_reason: null,
  created_at: "2026-04-10T08:59:00Z",
  updated_at: "2026-04-10T09:15:00Z",
};

const stage = (overrides: Partial<RunPipelineHealthStage>): RunPipelineHealthStage => ({
  stage: "acquisition",
  status: "in_progress",
  detail: "Working through provider jobs.",
  updated_at: "2026-04-10T09:12:00Z",
  ...overrides,
});

describe("run decision support helpers", () => {
  it("explains run overview decisions for failed production runs", () => {
    const support = buildRunDecisionSupport({
      ...baseRun,
      mode: "production",
      status: "failed",
      failure_reason: "DI processing halted on schema mismatch.",
      completed_at: "2026-04-10T09:20:00Z",
    });

    expect(support.whyItMatters).toContain("production run");
    expect(support.whatIsBlocked).toContain("schema mismatch");
    expect(support.whatChangedRecently).toContain("failure outcome");
    expect(support.whatHappensIfIgnored).toContain("remains failed");
  });

  it("summarizes pipeline blockers and recent stage movement", () => {
    const health: RunPipelineHealth = {
      run_id: baseRun.run_id,
      source_id: baseRun.source_id,
      source_version_id: baseRun.source_version_id,
      mode: baseRun.mode,
      run_status: "running",
      overall_status: "blocked",
      stages: [
        stage({ stage: "acquisition", status: "blocked", detail: "Waiting on provider retry." }),
        stage({
          stage: "document_intelligence",
          status: "in_progress",
          updated_at: "2026-04-10T09:18:00Z",
          detail: "DI is still processing captured resources.",
        }),
      ],
      processing_status_event_count: 4,
      document_lifecycle_event_count: 2,
    };

    const support = buildPipelineDecisionSupport({ run: baseRun, health });

    expect(support.whyItMatters).toContain("preview run");
    expect(support.whatIsBlocked).toContain("acquisition");
    expect(support.whatChangedRecently).toContain("document intelligence");
    expect(support.whatHappensIfIgnored).toContain("stays blocked");
  });

  it("tells the operator downstream stages are dead once the run terminally failed", () => {
    const health: RunPipelineHealth = {
      run_id: baseRun.run_id,
      source_id: baseRun.source_id,
      source_version_id: baseRun.source_version_id,
      mode: baseRun.mode,
      run_status: "failed",
      overall_status: "failed",
      stages: [
        stage({ stage: "acquisition", status: "failed", detail: "Provider dispatch failed." }),
        stage({
          stage: "projection",
          status: "pending",
          updated_at: null,
          detail: "Awaiting DI processing signal before projection stage starts.",
        }),
      ],
      processing_status_event_count: 0,
      document_lifecycle_event_count: 0,
    };

    const support = buildPipelineDecisionSupport({ run: { ...baseRun, status: "failed" }, health });

    expect(support.whatIsBlocked).toContain("will never run: projection");
    expect(support.whatHappensIfIgnored).toContain("already ended as failed");
    // ...and it must not imply the run will move on its own.
    expect(support.whatHappensIfIgnored).not.toContain("stays blocked");
  });
});
