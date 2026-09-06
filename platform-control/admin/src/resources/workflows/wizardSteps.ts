/**
 * The onboarding stepper's model, kept separate from its rendering so it can be
 * unit-tested without a DOM.
 *
 * The five steps are the operator's view of the loop. They are NOT the same
 * thing as `WizardRunState` — the server has nine states, several of which
 * (`ScaledRun`, `ReviewRouting`, `FinalizePublish`, `MonitorAndDrift`) all sit
 * *after* the only decision an operator makes here. Collapsing them into one
 * "running" step is deliberate; presenting nine states as nine things to do
 * would imply four decisions that do not exist.
 */
import type { WizardProject, WizardRunState, WizardRunStatus } from "../../lib/admin/dataProvider";

export type StepId = "scope" | "discovery" | "pilot" | "decision" | "scaled";

export type StepStatus = "done" | "current" | "pending" | "blocked";

export interface Step {
  id: StepId;
  label: string;
  /** What this step establishes, in the operator's terms. */
  detail: string;
}

export const STEPS: Step[] = [
  {
    id: "scope",
    label: "Scope",
    detail: "Which jurisdiction and authority this source belongs to.",
  },
  {
    id: "discovery",
    label: "Discovery plan",
    detail: "Which blueprint template to acquire through, and what it points at.",
  },
  {
    id: "pilot",
    label: "Pilot run",
    detail: "A sample acquisition against the live source. Evidence, not production ingest.",
  },
  {
    id: "decision",
    label: "Decision",
    detail: "Approve to scale, or reject. This is the only gate an operator holds here.",
  },
  {
    id: "scaled",
    label: "Scaled run",
    detail: "The full run and everything after it — review routing, publish, drift.",
  },
];

/** Server states that mean "the pilot has been approved and work continues". */
const POST_GATE_STATES: WizardRunState[] = [
  "ScaledRun",
  "ReviewRouting",
  "FinalizePublish",
  "MonitorAndDrift",
];

export function isTerminal(state: WizardRunState | undefined): boolean {
  return state === "GateExpired";
}

/**
 * Resolve each step's status from the project and (optional) run.
 *
 * `GateExpired` marks the DECISION step `blocked`, never `pending` and never
 * `done`: nobody decided, the gate closed, and the only way forward is a new
 * pilot run. Rendering it as merely incomplete would invite an operator to wait
 * for something that will never arrive.
 */
export function resolveStepStatuses(
  project: WizardProject | null,
  run: WizardRunStatus | null,
): Record<StepId, StepStatus> {
  const hasScope = Boolean(project && Object.keys(project.scope).length > 0);
  const hasPlan = Boolean(project && Object.keys(project.discovery_plan).length > 0);
  const state = run?.state;
  const expired = isTerminal(state);
  const atGate = state === "HumanGateApproval";
  const postGate = state !== undefined && POST_GATE_STATES.includes(state);

  const statuses: Record<StepId, StepStatus> = {
    scope: hasScope ? "done" : "current",
    discovery: hasScope ? (hasPlan ? "done" : "current") : "pending",
    pilot: "pending",
    decision: "pending",
    scaled: "pending",
  };

  if (hasScope && hasPlan) {
    if (!run) {
      statuses.pilot = "current";
    } else if (expired) {
      // The pilot itself completed; it is the decision that lapsed.
      statuses.pilot = "done";
      statuses.decision = "blocked";
    } else if (atGate) {
      statuses.pilot = "done";
      statuses.decision = "current";
    } else if (postGate) {
      statuses.pilot = "done";
      statuses.decision = "done";
      statuses.scaled = "current";
    } else {
      statuses.pilot = "current";
    }
  }

  return statuses;
}

/** Human-readable line for the run's current server state. */
export function describeRunState(run: WizardRunStatus | null): string {
  if (!run) return "No pilot run started yet.";
  switch (run.state) {
    case "HumanGateApproval":
      return "Waiting on an operator decision. Nothing scales until you approve.";
    case "GateExpired":
      return "The human gate expired before anyone decided. This run is terminal — restart to run a fresh pilot. It did not auto-approve, and it never will.";
    case "ScaledRun":
      return "Approved. The full run is in progress.";
    case "ReviewRouting":
      return "Records are being routed for review.";
    case "FinalizePublish":
      return "Finalising and publishing.";
    case "MonitorAndDrift":
      return "Live. Monitoring for drift.";
    default:
      return `In progress (${run.state}).`;
  }
}
