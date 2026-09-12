/**
 * The two derivations an operator needs off a run, ported from the CLI so the
 * panel and `evidara workflow coverage` say the same words.
 *
 *   1. **Why did nothing happen?** — `diagnoseRunStall`, a port of
 *      `diagnose_stall` (`tools/evidara-cli/src/evidara_cli/coverage.py:277-318`).
 *   2. **Does this run justify flipping the key?** — `acceptanceEvidenceVerdict`,
 *      a port of `acceptance_evidence_verdict` (`coverage.py:351-388`).
 *
 * Ported, not reinvented. AGENTS.md honesty rule 8: refusals are *codes with
 * remedies*, and the codes an operator reads on screen must be the codes an agent
 * reads on stdout. Every slug and every detail sentence below is the CLI's,
 * verbatim where the sentence carries the reasoning. A fifth private vocabulary
 * would make the two surfaces disagree about the same run.
 *
 * The panel had neither derivation. A run stuck PENDING got exactly one sentence
 * — *"The run is queued. Review readiness and wait for the first stage update."*
 * (`RunShowV2.tsx:52-54`) — for six distinct causes, one of which
 * (`no_dispatch_worker`) reads like a broken provider and is not one, and another
 * of which (`publish_path_disabled`) is a **green** run over a dead pipeline.
 *
 * The derivation belongs on the server eventually — the IA proposal's item 4, and
 * the CLI already carries a refusal code for two implementations drifting
 * (`classification_disagrees_with_server`, `coverage.py:452`). Until that lands,
 * this port is the panel's only access to it, and the tests beside this file pin
 * it to the CLI's behaviour rather than to a UI expectation.
 *
 * #950 changed the diagnosis on **both** sides together, for that reason: the two
 * new causes (`run_failed`, `too_early_to_diagnose`) and the three tightened
 * branches exist verbatim in `coverage.py` as well. A fix landed here alone would
 * have created exactly the drift this header warns about.
 */

// ---------------------------------------------------------------------------
// Stall diagnosis — coverage.py:227-269
// ---------------------------------------------------------------------------

export const STALL_RUN_REFUSED = "run_refused_by_lock";
export const STALL_NO_DISPATCH_WORKER = "no_dispatch_worker";
export const STALL_PUBLISH_PATH_DISABLED = "publish_path_disabled";
export const STALL_DI_CONSUMER_SILENT = "di_consumer_silent";
export const STALL_PROJECTION_STALLED = "projection_stalled";
export const STALL_SEARCH_PENDING = "search_projection_pending";
/**
 * The run failed on its own terms and recorded why. Not a stall signature derived
 * from stage state — the run's own `failure_reason`, which the panel already
 * renders 200px above and the diagnosis used to ignore (#950).
 */
export const STALL_RUN_FAILED = "run_failed";
/**
 * No cause can be named yet, and that is different from "nothing is wrong".
 *
 * A run still in flight has downstream stages `pending` because nothing has asked
 * them to do anything, not because a bridge is broken. Distinguishing "not yet"
 * from "stuck" needs elapsed time, which this snapshot does not carry — so the
 * honest answer is that the question is premature (ADR-0052: a diagnosis that
 * cannot be made is not a clean bill of health).
 */
export const STALL_TOO_EARLY = "too_early_to_diagnose";
export const STALL_UNKNOWN = "unknown";

export type StallCause =
  | typeof STALL_RUN_REFUSED
  | typeof STALL_NO_DISPATCH_WORKER
  | typeof STALL_PUBLISH_PATH_DISABLED
  | typeof STALL_DI_CONSUMER_SILENT
  | typeof STALL_PROJECTION_STALLED
  | typeof STALL_SEARCH_PENDING
  | typeof STALL_RUN_FAILED
  | typeof STALL_TOO_EARLY
  | typeof STALL_UNKNOWN;

const STALL_DETAIL: Record<StallCause, string> = {
  [STALL_RUN_REFUSED]:
    "The run was refused by the ADR-0030 two-key lock and persisted as FAILED with `refused: true`. This is not a stall — read the failure reason and fix the key it names. Go to the template's config and code keys, not to provider debugging.",
  [STALL_NO_DISPATCH_WORKER]:
    "The run was accepted but never left PENDING, so nothing dispatched it. platform-control persists the run before dispatch, so a PENDING run with no acquisition progress means no worker picked it up: check that the dispatcher for the configured `run_dispatch_backend` is actually running. A local compose stack does not start a worker for every provider.",
  [STALL_PUBLISH_PATH_DISABLED]:
    "Acquisition finished and captured resources, but document-intelligence received zero processing-status events. The publish path is the usual cause: PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND defaults to `noop`, so platform-control captures the documents, reports the run `completed`, and publishes nothing. Set it to `nats` (with PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=s3) and re-run.",
  [STALL_DI_CONSUMER_SILENT]:
    "document-intelligence acknowledged the run but has not progressed. Check the DI consumer container is up and reading the stream.",
  [STALL_PROJECTION_STALLED]:
    "DI reported processing but no document-lifecycle events were projected. Check the projection bridge between DI and legal-search.",
  [STALL_SEARCH_PENDING]:
    "Projection has run but the search stage has not reported. Give the index a moment, then assert searchability directly.",
  [STALL_RUN_FAILED]:
    "The run failed and was not refused by the two-key lock, and no failure reason was recorded. That is unrecorded, not absent — read the run's provider jobs and the dispatcher logs. The stages below say how far it got, not why it stopped.",
  [STALL_TOO_EARLY]:
    "The run is still executing, so the stages after acquisition are pending because nothing has asked them to do anything yet. That is the expected shape of a run in flight, not a stall — no downstream cause can be named while acquisition is still going, because telling “not yet” from “stuck” needs elapsed time this snapshot does not carry. Watch the acquisition stage and read this panel again once the run reaches a terminal state.",
  [STALL_UNKNOWN]: "No known stall signature matched. Inspect the pipeline-health stages directly.",
};

/** Short operator-facing name for the cause chip. */
const STALL_LABEL: Record<StallCause, string> = {
  [STALL_RUN_REFUSED]: "Refused by the two-key lock",
  [STALL_NO_DISPATCH_WORKER]: "No dispatch worker",
  [STALL_PUBLISH_PATH_DISABLED]: "Publish path disabled",
  [STALL_DI_CONSUMER_SILENT]: "DI consumer silent",
  [STALL_PROJECTION_STALLED]: "Projection stalled",
  [STALL_SEARCH_PENDING]: "Search projection pending",
  [STALL_RUN_FAILED]: "Run failed",
  [STALL_TOO_EARLY]: "Too early to say",
  [STALL_UNKNOWN]: "Unknown",
};

export interface StallDiagnosis {
  cause: StallCause;
  label: string;
  detail: string;
  /**
   * True when the cause names something to act on.
   *
   * False for `too_early_to_diagnose` and `unknown` — the two outcomes that are
   * *not* a finding. A caller must render neither as a defect and neither as
   * health: "no answer yet" is a third state beside "absent" and "zero"
   * (ADR-0052).
   */
  isDiagnosed: boolean;
}

interface StallHealthInput {
  stages: { stage: string; status: string }[];
  processing_status_event_count: number;
  document_lifecycle_event_count: number;
}

interface StallRunInput {
  status: string;
  refused?: boolean;
  /**
   * The run's own recorded reason for failing. Absent/`null` is a real
   * distinction from a recorded reason: it means nobody wrote one down, and the
   * diagnosis says exactly that rather than implying there was nothing to say.
   */
  failure_reason?: string | null;
}

const stageStatus = (health: StallHealthInput | null, name: string): string | null =>
  health?.stages.find((stage) => stage.stage === name)?.status ?? null;

/**
 * Name the likely cause of a run that has not reached the requested state.
 *
 * `health` is nullable because the pipeline-health fetch can fail independently
 * of the run: a broken read degrades to `unknown` with the stages unreadable, not
 * to a confident cause derived from zeros.
 */
export const diagnoseRunStall = (
  run: StallRunInput,
  health: StallHealthInput | null,
): StallDiagnosis => {
  const cause = ((): StallCause => {
    if (run.refused === true) {
      return STALL_RUN_REFUSED;
    }
    const status = run.status.toLowerCase();
    if (status === "pending") {
      return STALL_NO_DISPATCH_WORKER;
    }
    if (status === "failed") {
      // Ask what the run's own status already says before deriving anything from
      // stage state. Doing it the other way round is what rendered a recorded
      // `failure_reason` as `unknown` (#950). No health snapshot is needed here.
      return STALL_RUN_FAILED;
    }
    if (!health) {
      // No health snapshot: every branch below reads it, and reading zeros off a
      // failed fetch would name `publish_path_disabled` on a healthy run.
      return STALL_UNKNOWN;
    }
    const processingEvents = health.processing_status_event_count;
    const lifecycleEvents = health.document_lifecycle_event_count;
    if (status === "completed" && processingEvents === 0) {
      return STALL_PUBLISH_PATH_DISABLED;
    }
    if (status === "running" || status === "in_progress") {
      // The run has not finished, so every stage after acquisition is pending by
      // construction. Reading those pendings as a downstream cause is how a
      // healthy young run got sent to debug the projection bridge (#950).
      return STALL_TOO_EARLY;
    }
    const di = stageStatus(health, "document_intelligence");
    if ((di === "pending" || di === "in_progress") && processingEvents > 0) {
      return STALL_DI_CONSUMER_SILENT;
    }
    const projection = stageStatus(health, "projection");
    if (
      processingEvents > 0 &&
      lifecycleEvents === 0 &&
      (projection === "pending" || projection === "in_progress")
    ) {
      // `processingEvents > 0` is what this cause's own sentence has always
      // claimed — "DI reported processing but no document-lifecycle events were
      // projected" — and what the branch never actually checked.
      return STALL_PROJECTION_STALLED;
    }
    if (lifecycleEvents > 0 && stageStatus(health, "search") === "pending") {
      // Likewise: "Projection has run but the search stage has not reported" is
      // only true if projection emitted something.
      return STALL_SEARCH_PENDING;
    }
    return STALL_UNKNOWN;
  })();

  const recordedFailure = cause === STALL_RUN_FAILED ? (run.failure_reason ?? "").trim() : "";
  const detail = recordedFailure
    ? `The run failed and recorded why: “${recordedFailure}”. That is the diagnosis — read it before reading the stages, which say how far the run got, not why it stopped.`
    : STALL_DETAIL[cause];

  return {
    cause,
    label: STALL_LABEL[cause],
    detail,
    isDiagnosed: cause !== STALL_TOO_EARLY && cause !== STALL_UNKNOWN,
  };
};

// ---------------------------------------------------------------------------
// Acceptance-evidence verdict — coverage.py:325-388
// ---------------------------------------------------------------------------

export const EVIDENCE_RUN_REFUSED = "run_refused_by_lock";
export const EVIDENCE_RUN_NOT_COMPLETED = "run_not_completed";
export const EVIDENCE_MODE_NOT_ACCEPTANCE = "mode_not_acceptance";
export const EVIDENCE_EXECUTION_MODE_SHADOW = "execution_mode_shadow";
export const EVIDENCE_NO_CAPTURED_RESOURCES = "no_captured_resources";

export type EvidenceRefusalCode =
  | typeof EVIDENCE_RUN_REFUSED
  | typeof EVIDENCE_RUN_NOT_COMPLETED
  | typeof EVIDENCE_MODE_NOT_ACCEPTANCE
  | typeof EVIDENCE_EXECUTION_MODE_SHADOW
  | typeof EVIDENCE_NO_CAPTURED_RESOURCES;

const EVIDENCE_DETAIL: Record<EvidenceRefusalCode, string> = {
  [EVIDENCE_RUN_REFUSED]:
    "The run was refused by the two-key lock; it never reached the portal, so it evidences nothing.",
  [EVIDENCE_RUN_NOT_COMPLETED]: "Only a completed run can serve as acceptance evidence.",
  [EVIDENCE_MODE_NOT_ACCEPTANCE]:
    "ADR-0030 §6: acceptance evidence comes from a run recorded with `mode=acceptance`, so evidence is self-labelling and cannot be mistaken for production ingest.",
  [EVIDENCE_EXECUTION_MODE_SHADOW]:
    "ADR-0030 §2: a SHADOW version is routed to the cassette provider and replays fixtures. It never touches the live portal, so it proves nothing about it and CANNOT serve as acceptance evidence — no matter how green it looks.",
  [EVIDENCE_NO_CAPTURED_RESOURCES]:
    "The run captured zero resources, so there is nothing for the gates to have asserted over.",
};

export interface EvidenceRefusal {
  code: EvidenceRefusalCode;
  detail: string;
}

export interface AcceptanceEvidenceVerdict {
  isAcceptanceEvidence: boolean;
  refusals: EvidenceRefusal[];
  /**
   * The version's execution mode, or `null` when the version could not be
   * resolved. `null` is **not** `live`: `GET /v1/versions/{id}` does not exist
   * (`routers/versions.py` serves only approve/reject/patch), so this is joined
   * through `GET /v1/sources/{source_id}/versions` and the join can miss.
   */
  executionMode: string | null;
  /** True when the SHADOW check could not be made, so the verdict is incomplete. */
  executionModeUnknown: boolean;
}

/**
 * Decide whether a run may be cited as ADR-0030 acceptance evidence.
 *
 * Refuses loudly rather than reporting a green-looking run as evidence. The
 * SHADOW refusal is the one ADR-0030 §2 calls out by name, and it is the reason
 * `executionMode` has to be joined from the **source version**
 * (`schemas/source.py:466`) — `RunResponse` has no such field
 * (`schemas/run.py:85-110`), so a run detail that does not make the join cannot
 * evaluate it at all.
 *
 * When the join fails, `executionModeUnknown` is set and the SHADOW refusal is
 * simply not evaluated. It is not silently passed: the caller renders the check
 * as *unverified*, never as green. A pass with an unmade check is #744's defect.
 */
export const acceptanceEvidenceVerdict = ({
  run,
  executionMode,
}: {
  run: { status: string; mode: string; refused?: boolean; captured_resources_count: number };
  executionMode: string | null | undefined;
}): AcceptanceEvidenceVerdict => {
  const refusals: EvidenceRefusalCode[] = [];

  if (run.refused === true) {
    refusals.push(EVIDENCE_RUN_REFUSED);
  }
  if (run.status.toLowerCase() !== "completed") {
    refusals.push(EVIDENCE_RUN_NOT_COMPLETED);
  }
  if (run.mode.toLowerCase() !== "acceptance") {
    refusals.push(EVIDENCE_MODE_NOT_ACCEPTANCE);
  }
  const resolvedExecutionMode = executionMode ?? null;
  if (resolvedExecutionMode !== null && resolvedExecutionMode.toLowerCase() === "shadow") {
    refusals.push(EVIDENCE_EXECUTION_MODE_SHADOW);
  }
  if (run.captured_resources_count <= 0) {
    refusals.push(EVIDENCE_NO_CAPTURED_RESOURCES);
  }

  return {
    isAcceptanceEvidence: refusals.length === 0,
    refusals: refusals.map((code) => ({ code, detail: EVIDENCE_DETAIL[code] })),
    executionMode: resolvedExecutionMode,
    executionModeUnknown: resolvedExecutionMode === null,
  };
};

/**
 * What a pass here does **not** cover.
 *
 * The acceptance harness computes `skipped_gates` and `environment`
 * (`scripts/ch-fedlex-compose-e2e.sh:578-590`) and writes them into a bundle
 * under `docs/runbooks/evidence/` — ~127 MB of repo files with no runtime path
 * whatsoever: no `StaticFiles`, no `.mount()`, not in the mkdocs nav. ADR-0044 §3
 * names the consequence: the number "dies in a file under /tmp" while the person
 * flipping the key is looking at this screen.
 *
 * So this panel renders the verdict from the run alone and says, in words, that
 * the two gate fields are **not available** — absent, never green. A skipped gate
 * is unverified (#744), and `environment` is not a detail either: every dog-axis
 * bundle on `main` records `compose-local`, so a production flip justified by a
 * laptop run is a different claim from the one a green badge appears to make.
 *
 * Serving them means the harness POSTing its `summary.json` to platform-control
 * as a record keyed on `run_id` — deliberately not static-mounting the directory,
 * which would put operator evidence back inside the image, the exact defect
 * ADR-0035 fixed for the config key. That endpoint does not exist yet.
 */
export const ACCEPTANCE_GATE_COVERAGE_UNAVAILABLE =
  "Gate coverage unavailable. The harness records `skipped_gates` and `environment` in an acceptance bundle under docs/runbooks/evidence/, which no runtime serves — so this panel cannot show them. Treat them as UNVERIFIED, not as passed: a skipped gate is not a green gate (#744), and every bundle on main records environment `compose-local`, not production.";
