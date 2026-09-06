import { describe, expect, it } from "vitest";
import type { WizardProject, WizardRunState, WizardRunStatus } from "../../lib/admin/dataProvider";
import { describeRunState, isTerminal, resolveStepStatuses, STEPS } from "./wizardSteps";

function project(over: Partial<WizardProject> = {}): WizardProject {
  return {
    wizard_project_id: "wpr_test",
    name: "test",
    status: "active",
    scope: {},
    discovery_plan: {},
    created_at: "2026-09-06T00:00:00Z",
    updated_at: "2026-09-06T00:00:00Z",
    ...over,
  };
}

function run(state: WizardRunState): WizardRunStatus {
  return {
    wizard_run_id: "wrn_test",
    wizard_project_id: "wpr_test",
    workflow_id: null,
    state,
    state_entered_at: "2026-09-06T00:00:00Z",
    progress: { total_nodes: 0, processed_nodes: 0, routed_to_review: 0, accepted_records: 0 },
    quality: { confidence_distribution: {}, conflict_count: 0, review_backlog: 0 },
    health: { retry_counters: {}, last_errors: [], next_retry_window: null },
    failure_reason: null,
    created_at: "2026-09-06T00:00:00Z",
    updated_at: "2026-09-06T00:00:00Z",
  };
}

const scoped = project({ scope: { jurisdiction_id: "jur_ch_federal" } });
const planned = project({
  scope: { jurisdiction_id: "jur_ch_federal" },
  discovery_plan: { overlay_id: "ch" },
});

describe("resolveStepStatuses", () => {
  it("starts on scope with nothing filled in", () => {
    const s = resolveStepStatuses(project(), null);
    expect(s.scope).toBe("current");
    expect(s.discovery).toBe("pending");
  });

  it("advances to the discovery plan once scope is saved", () => {
    const s = resolveStepStatuses(scoped, null);
    expect(s.scope).toBe("done");
    expect(s.discovery).toBe("current");
    expect(s.pilot).toBe("pending");
  });

  it("offers the pilot once scope and plan are both saved", () => {
    const s = resolveStepStatuses(planned, null);
    expect(s.discovery).toBe("done");
    expect(s.pilot).toBe("current");
  });

  it("puts the decision in front of the operator at the human gate", () => {
    const s = resolveStepStatuses(planned, run("HumanGateApproval"));
    expect(s.pilot).toBe("done");
    expect(s.decision).toBe("current");
    expect(s.scaled).toBe("pending");
  });

  /**
   * The load-bearing case. `GateExpired` is terminal: nobody decided, and the
   * server will never auto-approve a fan-out of crawls against live government
   * portals. If this renders as `pending` the operator is invited to wait for
   * something that cannot arrive; if it renders as `done` the UI claims a
   * decision nobody made. It must be `blocked`.
   *
   * Delete the `expired` branch in `resolveStepStatuses` and this test fails.
   */
  it("marks an expired gate blocked — never pending, never done", () => {
    const s = resolveStepStatuses(planned, run("GateExpired"));
    expect(s.decision).toBe("blocked");
    expect(s.decision).not.toBe("pending");
    expect(s.decision).not.toBe("done");
    expect(s.scaled).toBe("pending");
  });

  it.each([
    "ScaledRun",
    "ReviewRouting",
    "FinalizePublish",
    "MonitorAndDrift",
  ] as const)("treats %s as past the gate", (state) => {
    const s = resolveStepStatuses(planned, run(state));
    expect(s.decision).toBe("done");
    expect(s.scaled).toBe("current");
  });
});

describe("isTerminal", () => {
  it("is true only for GateExpired", () => {
    expect(isTerminal("GateExpired")).toBe(true);
    expect(isTerminal("HumanGateApproval")).toBe(false);
    expect(isTerminal(undefined)).toBe(false);
  });
});

describe("describeRunState", () => {
  it("says an expired gate did not and will not auto-approve", () => {
    const text = describeRunState(run("GateExpired"));
    expect(text).toMatch(/terminal/i);
    expect(text).toMatch(/never/i);
  });

  it("says nothing scales while the gate is open", () => {
    expect(describeRunState(run("HumanGateApproval"))).toMatch(/nothing scales/i);
  });
});

describe("STEPS", () => {
  it("names the five operator steps in loop order", () => {
    expect(STEPS.map((s) => s.id)).toEqual(["scope", "discovery", "pilot", "decision", "scaled"]);
  });
});
