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
  STALL_RUN_FAILED,
  STALL_RUN_REFUSED,
  STALL_SEARCH_PENDING,
  STALL_TOO_EARLY,
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

  // -------------------------------------------------------------------------
  // #950: wrong in both directions — a cause that cannot be true on a healthy
  // running run, and an abstention on a failed run that recorded its reason.
  // -------------------------------------------------------------------------

  /**
   * `run_demo_running` as the demo seed writes it
   * (`platform-control/src/platform_control/seed_demo_runs.py:117-123`):
   * acquisition in flight, everything downstream pending, no events yet.
   *
   * This shape is the *whole* point of the test below — it is exactly the input
   * the old `lifecycleEvents === 0 && projection === "pending"` branch fired on.
   * The assertion right underneath pins that, so the fixture cannot quietly drift
   * into one that never reaches the branch at all.
   */
  const youngRunningHealth = () =>
    health({
      stages: [
        { stage: "acquisition", status: "in_progress" },
        { stage: "document_intelligence", status: "pending" },
        { stage: "projection", status: "pending" },
        { stage: "search", status: "pending" },
      ],
      processing_status_event_count: 0,
      document_lifecycle_event_count: 0,
    });

  it("refuses to diagnose a running run that has not reached DI yet", () => {
    const snapshot = youngRunningHealth();

    // The fixture really is the one the false positive was derived from: zero
    // lifecycle events with the projection stage pending. If this ever stops
    // holding, the assertion below would pass for the wrong reason.
    expect(snapshot.document_lifecycle_event_count).toBe(0);
    expect(snapshot.stages.find((s) => s.stage === "projection")?.status).toBe("pending");

    const diagnosis = diagnoseRunStall({ status: "running" }, snapshot);
    expect(diagnosis.cause).toBe(STALL_TOO_EARLY);
    expect(diagnosis.isDiagnosed).toBe(false);
    // The specific wrong answer #950 reported, named so the regression is legible.
    expect(diagnosis.cause).not.toBe(STALL_PROJECTION_STALLED);
    expect(diagnosis.detail).not.toContain("projection bridge");
    // "Too early" is not "nothing is wrong" (ADR-0052).
    expect(diagnosis.detail).toContain("not a stall");
  });

  it("names the recorded failure reason instead of abstaining", () => {
    const reason =
      "provider returned HTTP 503 for 2 of 2 captured resources, after 3 retries against the upstream host";
    const diagnosis = diagnoseRunStall({ status: "failed", failure_reason: reason }, health());
    expect(diagnosis.cause).toBe(STALL_RUN_FAILED);
    expect(diagnosis.cause).not.toBe(STALL_UNKNOWN);
    expect(diagnosis.isDiagnosed).toBe(true);
    expect(diagnosis.detail).toContain(reason);
  });

  it("says a failure reason is unrecorded rather than inventing a stage cause", () => {
    // Absent is not zero and not unknown: nobody wrote a reason down, and the
    // panel says so instead of reading the stages for a cause they cannot carry.
    const diagnosis = diagnoseRunStall({ status: "failed", failure_reason: null }, health());
    expect(diagnosis.cause).toBe(STALL_RUN_FAILED);
    expect(diagnosis.detail).toContain("no failure reason was recorded");
    expect(diagnosis.detail).toContain("not absent");
  });

  it("keeps the lock refusal ahead of the plain failure branch", () => {
    // A refusal is persisted as FAILED with `refused: true`; it must keep naming
    // the key, not the generic failure.
    expect(
      diagnoseRunStall(
        { status: "failed", refused: true, failure_reason: "config key not set" },
        health(),
      ).cause,
    ).toBe(STALL_RUN_REFUSED);
  });

  it("needs no health snapshot to diagnose a failed run", () => {
    expect(diagnoseRunStall({ status: "failed", failure_reason: "boom" }, null).cause).toBe(
      STALL_RUN_FAILED,
    );
  });

  it("will not claim a projection stall when DI never reported processing", () => {
    // The `projection_stalled` sentence says "DI reported processing but no
    // document-lifecycle events were projected". With zero processing events
    // that claim is false, so the honest answer is that nothing matched.
    const diagnosis = diagnoseRunStall(
      { status: "cancelled" },
      health({
        stages: [
          { stage: "projection", status: "pending" },
          { stage: "search", status: "pending" },
        ],
        processing_status_event_count: 0,
        document_lifecycle_event_count: 0,
      }),
    );
    expect(diagnosis.cause).toBe(STALL_UNKNOWN);
    expect(diagnosis.cause).not.toBe(STALL_PROJECTION_STALLED);
    // …and not the next branch down either: "projection has run" is equally false.
    expect(diagnosis.cause).not.toBe(STALL_SEARCH_PENDING);
    expect(diagnosis.isDiagnosed).toBe(false);
  });

  it("marks a named cause as diagnosed and an abstention as not", () => {
    expect(diagnoseRunStall({ status: "pending" }, health()).isDiagnosed).toBe(true);
    expect(diagnoseRunStall({ status: "completed" }, null).isDiagnosed).toBe(false);
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
