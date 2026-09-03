import { describe, expect, it } from "vitest";
import {
  acceptanceEvidenceVerdict,
  diagnoseRunStall,
  EVIDENCE_EXECUTION_MODE_SHADOW,
  EVIDENCE_MODE_NOT_ACCEPTANCE,
  EVIDENCE_NO_CAPTURED_RESOURCES,
  EVIDENCE_RUN_NOT_COMPLETED,
  EVIDENCE_RUN_REFUSED,
  STALL_DI_CONSUMER_SILENT,
  STALL_NO_DISPATCH_WORKER,
  STALL_PROJECTION_STALLED,
  STALL_PUBLISH_PATH_DISABLED,
  STALL_RUN_REFUSED,
  STALL_SEARCH_PENDING,
  STALL_UNKNOWN,
} from "./runDiagnosis";

const health = (
  overrides: Partial<{
    stages: { stage: string; status: string }[];
    processing_status_event_count: number;
    document_lifecycle_event_count: number;
  }> = {},
) => ({
  stages: [
    { stage: "acquisition", status: "complete" },
    { stage: "document_intelligence", status: "complete" },
    { stage: "projection", status: "complete" },
    { stage: "search", status: "complete" },
  ],
  processing_status_event_count: 5,
  document_lifecycle_event_count: 5,
  ...overrides,
});

describe("diagnoseRunStall", () => {
  it("names a lock refusal before anything else and sends the operator to the key", () => {
    const diagnosis = diagnoseRunStall({ status: "failed", refused: true }, health());
    expect(diagnosis.cause).toBe(STALL_RUN_REFUSED);
    expect(diagnosis.detail).toContain("two-key lock");
    expect(diagnosis.detail).toContain("not to provider debugging");
  });

  it("names the missing dispatcher rather than 'wait for the first stage update'", () => {
    // The generic PENDING copy sent an operator to wait on a run nothing would
    // ever pick up. `no_dispatch_worker` reads like a broken provider and is not.
    expect(diagnoseRunStall({ status: "pending" }, health()).cause).toBe(STALL_NO_DISPATCH_WORKER);
  });

  it("names a green run over a dead publish path", () => {
    // ADR-0032's context exactly: completed, zero DI events, publisher on `noop`.
    const diagnosis = diagnoseRunStall(
      { status: "completed" },
      health({ processing_status_event_count: 0 }),
    );
    expect(diagnosis.cause).toBe(STALL_PUBLISH_PATH_DISABLED);
    expect(diagnosis.detail).toContain("PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND");
  });

  it("distinguishes a silent DI consumer from a stalled projection", () => {
    expect(
      diagnoseRunStall(
        { status: "completed" },
        health({
          stages: [{ stage: "document_intelligence", status: "in_progress" }],
          processing_status_event_count: 3,
        }),
      ).cause,
    ).toBe(STALL_DI_CONSUMER_SILENT);

    expect(
      diagnoseRunStall(
        { status: "completed" },
        health({
          stages: [{ stage: "projection", status: "pending" }],
          document_lifecycle_event_count: 0,
        }),
      ).cause,
    ).toBe(STALL_PROJECTION_STALLED);
  });

  it("names a pending search projection", () => {
    expect(
      diagnoseRunStall(
        { status: "completed" },
        health({ stages: [{ stage: "search", status: "pending" }] }),
      ).cause,
    ).toBe(STALL_SEARCH_PENDING);
  });

  it("degrades to unknown when pipeline health could not be read", () => {
    // A broken read must not become a confident cause: reading zeros off a failed
    // fetch would name `publish_path_disabled` on a perfectly healthy run.
    expect(diagnoseRunStall({ status: "completed" }, null).cause).toBe(STALL_UNKNOWN);
    // …but a PENDING run needs no health snapshot to be diagnosed.
    expect(diagnoseRunStall({ status: "pending" }, null).cause).toBe(STALL_NO_DISPATCH_WORKER);
  });
});

const completedAcceptanceRun = {
  status: "completed",
  mode: "acceptance",
  refused: false,
  captured_resources_count: 12,
};

describe("acceptanceEvidenceVerdict", () => {
  it("passes a completed live acceptance run that captured something", () => {
    const verdict = acceptanceEvidenceVerdict({
      run: completedAcceptanceRun,
      executionMode: "live",
    });
    expect(verdict.isAcceptanceEvidence).toBe(true);
    expect(verdict.refusals).toEqual([]);
    expect(verdict.executionModeUnknown).toBe(false);
  });

  it("refuses a fully green SHADOW run — the refusal ADR-0030 §2 names", () => {
    const verdict = acceptanceEvidenceVerdict({
      run: completedAcceptanceRun,
      executionMode: "shadow",
    });
    expect(verdict.isAcceptanceEvidence).toBe(false);
    expect(verdict.refusals.map((r) => r.code)).toEqual([EVIDENCE_EXECUTION_MODE_SHADOW]);
  });

  it("does not pass the SHADOW check when the version could not be resolved", () => {
    // There is no `GET /v1/versions/{id}`, so the join can miss. An unmade check
    // is unverified, never green — the caller must render it as such.
    const verdict = acceptanceEvidenceVerdict({
      run: completedAcceptanceRun,
      executionMode: null,
    });
    expect(verdict.executionModeUnknown).toBe(true);
    expect(verdict.refusals).toEqual([]);
    // The verdict is not asserted as complete; the panel says the check is unmade.
    expect(verdict.executionMode).toBeNull();
  });

  it("reports every applicable refusal, not just the first", () => {
    const verdict = acceptanceEvidenceVerdict({
      run: { status: "failed", mode: "production", refused: true, captured_resources_count: 0 },
      executionMode: "shadow",
    });
    expect(verdict.refusals.map((r) => r.code)).toEqual([
      EVIDENCE_RUN_REFUSED,
      EVIDENCE_RUN_NOT_COMPLETED,
      EVIDENCE_MODE_NOT_ACCEPTANCE,
      EVIDENCE_EXECUTION_MODE_SHADOW,
      EVIDENCE_NO_CAPTURED_RESOURCES,
    ]);
  });

  it("refuses a preview run as evidence", () => {
    const verdict = acceptanceEvidenceVerdict({
      run: { ...completedAcceptanceRun, mode: "preview" },
      executionMode: "live",
    });
    expect(verdict.refusals.map((r) => r.code)).toEqual([EVIDENCE_MODE_NOT_ACCEPTANCE]);
  });
});
