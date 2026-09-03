/**
 * The M15 read surfaces on the run detail: what this run refused, what it
 * captured versus published, whether the mirror was proven, and whether any of
 * it justifies flipping a template's config key.
 *
 * Every number here already existed on the wire and reached no screen. The four
 * panels below are, in order:
 *
 * - `RunRefusalBanner` — `run.refused` (ADR-0035 / #634). Rendered by nothing
 *   until now, so a refused dispatch looked like a provider failure and sent
 *   operators to debug something that was never called.
 * - `RunStallPanel` — the six named stall causes from the CLI, replacing one
 *   sentence that covered all of them.
 * - `RunAcceptanceEvidencePanel` — the ADR-0030 verdict, including the
 *   `execution_mode` join that lives on the **source version**
 *   (`schemas/source.py:466`), not on `RunResponse`.
 * - `RunCaptureLedgerPanel` — `captured` vs `published` as separate numbers, the
 *   per-resource refusal slugs grouped by reason, and the mirror-fidelity block.
 *
 * The honesty rules these panels are written against (OPERATOR_JOBS.md):
 * a missing denominator renders as a dash and never `0`; there are no ratios and
 * no progress bars anywhere in this file; a skipped or unmade gate renders as
 * *unverified*, never as green; and a broken read degrades to *unavailable*
 * rather than to zeros.
 */
"use client";

import { useGetList } from "ra-core";
import { useMemo } from "react";
import type {
  ProviderJobRecord,
  RunPipelineHealth,
  RunRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";
import { InlineAlert, Panel, Pill } from "../../ui/primitives";
import {
  groupRefusalsByReason,
  isUnverifiedMirrorStatus,
  readCaptureLedger,
  readMirrorFidelity,
} from "./providerJobPayload";
import {
  ACCEPTANCE_GATE_COVERAGE_UNAVAILABLE,
  acceptanceEvidenceVerdict,
  diagnoseRunStall,
} from "./runDiagnosis";

/** The em dash this panel uses for "no value", never a zero. */
const Dash = () => (
  <span className="text-[var(--foreground-faint)]" title="not recorded">
    —
  </span>
);

/**
 * One labelled number, or a dash when it was never recorded.
 *
 * `0` is a real measurement and renders as `0`; `null` is the absence of one and
 * renders as `—` with the caption saying so. Collapsing them is the single defect
 * this whole lane exists to stop.
 */
function Measure({
  label,
  value,
  caption,
  tone = "neutral",
}: {
  label: string;
  value: number | null;
  caption?: string;
  tone?: "neutral" | "critical" | "degraded";
}) {
  const toneClass =
    tone === "critical"
      ? "text-[var(--status-critical)]"
      : tone === "degraded"
        ? "text-[var(--status-degraded)]"
        : "text-[var(--foreground)]";
  return (
    <div className="rounded-[10px] border border-[var(--border-faint)] bg-white/80 p-3">
      <span className="block text-[11px] font-semibold uppercase tracking-[0.08em] leading-[1.2] text-[var(--foreground-subtle)]">
        {label}
      </span>
      <span className={`block text-[20px] font-semibold tabular-nums ${toneClass}`}>
        {value === null ? <Dash /> : value}
      </span>
      <span className="block text-[11px] text-[var(--foreground-subtle)]">
        {caption ?? (value === null ? "not recorded by the provider" : null)}
      </span>
    </div>
  );
}

function PanelHeading({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h2 className="text-[15px] font-semibold text-[var(--foreground)]">{title}</h2>
      <p className="text-[12px] text-[var(--foreground-subtle)]">{subtitle}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1. Refusal
// ---------------------------------------------------------------------------

/**
 * Renders only for a refused run, and leads the page when it does.
 *
 * `refused: true` means the dispatch was blocked by the ADR-0030 two-key lock
 * before anything was fetched. It is persisted as terminal FAILED, which is why
 * it has to say so loudly: without this the operator reads a red run and goes
 * looking for a provider defect that does not exist.
 */
export function RunRefusalBanner({ run }: { run: RunRecord }) {
  if (!run.refused) {
    return null;
  }
  return (
    <InlineAlert tone="warning" testId="run-refusal-banner">
      <div className="space-y-2">
        <p className="font-semibold text-[var(--foreground)]">
          This run was refused before dispatch
        </p>
        <p>
          The ADR-0030 two-key lock blocked it. Nothing was fetched, no provider was called and no
          document entered the corpus — the run exists as the record of what was attempted. Its
          status reads <code>failed</code> because a refusal is terminal, not because a provider
          failed.
        </p>
        {run.failure_reason ? (
          <p className="rounded-[8px] bg-white/70 px-3 py-2 font-mono text-[12px] text-[var(--foreground)]">
            {run.failure_reason}
          </p>
        ) : (
          <p>
            No refusal reason was recorded on this run, so which key blocked it is not readable here
            — check the template's config and code keys directly.
          </p>
        )}
        <p>
          The remedy is a key on the blueprint template, not provider debugging. The refusal records
          what was attempted and why it was blocked; it does not record who attempted it.
        </p>
      </div>
    </InlineAlert>
  );
}

// ---------------------------------------------------------------------------
// 2. Stall
// ---------------------------------------------------------------------------

/**
 * Names why nothing happened, instead of "wait for the first stage update".
 *
 * Hidden for a completed run whose pipeline reached search — there is no stall to
 * diagnose and a permanent "unknown" chip would be noise. Shown for every other
 * state, including a *green* run over a dead publish path, which is the case the
 * generic copy hid completely.
 */
export function RunStallPanel({
  run,
  health,
  healthIsPending,
  healthError,
}: {
  run: RunRecord;
  health: RunPipelineHealth | null;
  healthIsPending: boolean;
  healthError: unknown;
}) {
  const diagnosis = useMemo(
    () => diagnoseRunStall({ status: run.status, refused: run.refused }, health),
    [health, run.status, run.refused],
  );

  // Nothing to diagnose: a completed run that produced lifecycle events reached
  // the end of the pipeline.
  const healthy =
    run.status === "completed" &&
    !run.refused &&
    diagnosis.cause === "unknown" &&
    (health?.document_lifecycle_event_count ?? 0) > 0;
  if (healthy) {
    return null;
  }

  return (
    <Panel className="space-y-3 p-4" testId="run-stall-panel">
      <PanelHeading
        title="Why nothing happened"
        subtitle="The named cause, from the same vocabulary the CLI prints — not a generic 'wait and see'."
      />
      {healthIsPending ? (
        <p className="text-[13px] text-[var(--foreground-subtle)]">Reading pipeline health…</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill level={diagnosis.cause === "unknown" ? "neutral" : "degraded"}>
              {diagnosis.cause}
            </Pill>
            <Pill variant="meta">{diagnosis.label}</Pill>
          </div>
          <p className="text-[13px] text-[var(--foreground-muted)]">{diagnosis.detail}</p>
          {healthError ? (
            <p className="text-[12px] font-semibold text-[var(--status-critical)]">
              Pipeline health could not be read, so the stage-dependent causes were not evaluated.
              This is “not diagnosed”, not “nothing is wrong”.
            </p>
          ) : null}
        </>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// 3. Acceptance evidence
// ---------------------------------------------------------------------------

/**
 * Does this run justify flipping the key?
 *
 * The verdict is the CLI's, ported (`runDiagnosis.ts`), over five inputs — mode,
 * execution mode, status, `refused`, capture count. The `execution_mode` join is
 * the one the run detail could not make: it is on the source version, and there
 * is no `GET /v1/versions/{id}`, so it is resolved through the source's version
 * list and can legitimately miss. When it misses, the SHADOW check is reported as
 * **not made** rather than passed.
 *
 * `skipped_gates` and `environment` are reported as unavailable in every case —
 * the harness writes them into a repo bundle that no runtime serves. A green
 * verdict beside a hidden skip list is #744 rebuilt in React.
 */
export function RunAcceptanceEvidencePanel({ run }: { run: RunRecord }) {
  const versions = useGetList<SourceVersionRecord>(
    "source-versions",
    {
      pagination: { page: 1, perPage: 200 },
      sort: { field: "created_at", order: "DESC" },
      filter: { source_id: run.source_id },
    },
    { enabled: Boolean(run.source_id) },
  );

  const version = versions.data?.find((item) => item.source_version_id === run.source_version_id);
  // `undefined` while loading and on error alike: an unresolved version must not
  // be read as `live`.
  const executionMode =
    versions.isPending || versions.error ? null : (version?.execution_mode ?? null);

  const verdict = useMemo(
    () =>
      acceptanceEvidenceVerdict({
        run: {
          status: run.status,
          mode: run.mode,
          refused: run.refused,
          captured_resources_count: run.captured_resources_count,
        },
        executionMode,
      }),
    [executionMode, run.captured_resources_count, run.mode, run.refused, run.status],
  );

  // Never claim evidence while a required input is missing.
  const verdictIsComplete = verdict.isAcceptanceEvidence && !verdict.executionModeUnknown;

  return (
    <Panel className="space-y-3 p-4" testId="run-acceptance-evidence">
      <PanelHeading
        title="Acceptance evidence (ADR-0030)"
        subtitle="Whether this run may be cited when turning a template's config key on."
      />

      <div className="flex flex-wrap items-center gap-1.5">
        {verdictIsComplete ? (
          <Pill level="healthy">counts as acceptance evidence</Pill>
        ) : verdict.executionModeUnknown && verdict.refusals.length === 0 ? (
          <Pill level="degraded">verdict incomplete</Pill>
        ) : (
          <Pill level="critical">does not count as acceptance evidence</Pill>
        )}
        <Pill variant="meta">{`mode ${run.mode}`}</Pill>
        <Pill variant="meta">
          {verdict.executionModeUnknown
            ? "execution mode unknown"
            : `execution mode ${verdict.executionMode}`}
        </Pill>
        <Pill variant="meta">{`status ${run.status}`}</Pill>
        <Pill variant="meta">{`refused ${run.refused ? "yes" : "no"}`}</Pill>
        <Pill variant="meta">{`captured ${run.captured_resources_count}`}</Pill>
      </div>

      {verdict.refusals.length > 0 ? (
        <ul className="space-y-2">
          {verdict.refusals.map((refusal) => (
            <li
              key={refusal.code}
              className="rounded-[10px] border border-[var(--status-critical)]/25 bg-[var(--status-critical-subtle)] p-3"
            >
              <p className="font-mono text-[12px] font-semibold text-[var(--status-critical)]">
                {refusal.code}
              </p>
              <p className="mt-0.5 text-[13px] text-[var(--foreground-muted)]">{refusal.detail}</p>
            </li>
          ))}
        </ul>
      ) : null}

      {verdict.executionModeUnknown ? (
        <InlineAlert tone="warning" testId="run-execution-mode-unknown">
          <div className="space-y-1">
            <p className="font-semibold text-[var(--foreground)]">
              Execution mode could not be resolved
            </p>
            <p>
              {versions.error
                ? "The source's version list could not be read."
                : versions.isPending
                  ? "Still reading the source's version list."
                  : `No version ${run.source_version_id} was found on this source.`}{" "}
              The mode lives on the source version, not on the run, and there is no endpoint that
              fetches one version directly — so this check was <strong>not made</strong>. It is not
              a pass: a fully green SHADOW run replays cassettes and proves nothing about the live
              portal.
            </p>
          </div>
        </InlineAlert>
      ) : null}

      <InlineAlert tone="warning" testId="run-gate-coverage-unavailable">
        <div className="space-y-1">
          <p className="font-semibold text-[var(--foreground)]">
            Gate coverage: <span className="uppercase">unavailable</span>
          </p>
          <p>{ACCEPTANCE_GATE_COVERAGE_UNAVAILABLE}</p>
          <p className="flex flex-wrap gap-1.5">
            <Pill variant="meta">skipped_gates — unavailable</Pill>
            <Pill variant="meta">environment — unavailable</Pill>
          </p>
        </div>
      </InlineAlert>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// 4. Capture ledger, refusal slugs and mirror fidelity
// ---------------------------------------------------------------------------

/**
 * What the providers say they captured, published and refused — plus the mirror
 * check, when one ran.
 *
 * All of it is parsed out of `ProviderJobResponse.response_payload`, which the
 * contract types as `additionalProperties: true`. The copy says so: an operator
 * should know these numbers are read from an untyped payload rather than from a
 * field the API promises. Typing them is the right fix and a contract change.
 */
export function RunCaptureLedgerPanel({ run }: { run: RunRecord }) {
  const providerJobs = useGetList<ProviderJobRecord>(
    "run-provider-jobs",
    {
      pagination: { page: 1, perPage: 100 },
      sort: { field: "created_at", order: "DESC" },
      filter: { run_id: run.run_id },
    },
    { enabled: Boolean(run.run_id) },
  );

  const payloads = useMemo(
    () => (providerJobs.data ?? []).map((job) => job.response_payload),
    [providerJobs.data],
  );
  const ledger = useMemo(() => readCaptureLedger(payloads), [payloads]);
  const refusalGroups = useMemo(() => groupRefusalsByReason(payloads), [payloads]);
  const mirror = useMemo(() => readMirrorFidelity(payloads), [payloads]);

  if (providerJobs.isPending) {
    return (
      <Panel className="p-4" testId="run-capture-ledger">
        <p className="text-[13px] text-[var(--foreground-subtle)]">Reading provider jobs…</p>
      </Panel>
    );
  }

  if (providerJobs.error) {
    // Degrade to unavailable, never to zeros.
    return (
      <Panel className="space-y-2 p-4" testId="run-capture-ledger">
        <PanelHeading
          title="Capture ledger"
          subtitle="What this run captured, published and refused."
        />
        <InlineAlert tone="error">
          The provider jobs for this run could not be read, so the capture ledger is unavailable.
          These are not zeros — nothing about what this run captured, published or refused is known
          from this screen right now.
        </InlineAlert>
      </Panel>
    );
  }

  return (
    <Panel className="space-y-4 p-4" testId="run-capture-ledger">
      <PanelHeading
        title="Capture ledger"
        subtitle="Read from the provider jobs' untyped response payload — not from a field the API promises."
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Measure
          label="Captured"
          value={ledger.captured}
          caption={
            ledger.captured === null ? "not recorded by the provider" : "fetched from source"
          }
        />
        <Measure
          label="Published"
          value={ledger.published}
          tone={ledger.disagrees ? "critical" : "neutral"}
          caption={
            ledger.published === null
              ? "not recorded by the provider"
              : "handed to the corpus pipeline"
          }
        />
        <Measure
          label="Refused"
          value={ledger.refused}
          tone={ledger.refused ? "degraded" : "neutral"}
          caption={
            ledger.refused === null
              ? "not recorded by the provider"
              : ledger.hasRefusalDetail
                ? "with reasons, below"
                : "count only — no reasons recorded"
          }
        />
        <Measure label="Run artifacts" value={run.artifacts_count} caption="stored raw artifacts" />
      </div>

      {ledger.disagrees ? (
        <InlineAlert tone="error" testId="run-capture-publish-disagreement">
          <div className="space-y-1">
            <p className="font-semibold text-[var(--foreground)]">
              Captured and published disagree
            </p>
            <p>
              {ledger.captured} document(s) were captured and {ledger.published} were published.
              These are two different facts and the page shows both rather than one derived number.
              A discard reads as an empty run when only one is shown — and, in the other direction,
              a run whose status is red may still have put its documents in the corpus.
            </p>
          </div>
        </InlineAlert>
      ) : null}

      {ledger.captured !== null && ledger.published === null ? (
        <p className="text-[12px] text-[var(--foreground-subtle)]">
          This provider records no separate <code>published</code> count, so whether everything
          captured was published cannot be answered from the run record. Absent, not equal.
        </p>
      ) : null}

      {/* Per-resource refusals, grouped by the artifact_guard slug. */}
      <div className="space-y-2">
        <h3 className="text-[13px] font-semibold text-[var(--foreground)]">
          What this run refused, by reason
        </h3>
        {refusalGroups.length === 0 ? (
          <p className="text-[13px] text-[var(--foreground-subtle)]">
            {ledger.refused === null
              ? "No provider job recorded a refusal list, so whether anything was turned away is unknown — not zero."
              : ledger.refused === 0
                ? "No resource was refused by the capture guard on this run."
                : `${ledger.refused} resource(s) were refused but no reason slug was recorded, so they cannot be grouped.`}
          </p>
        ) : (
          <ul className="space-y-2">
            {refusalGroups.map((group) => (
              <li
                key={group.reason}
                className="rounded-[10px] border border-[var(--border-faint)] bg-white/80 p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[12px] font-semibold text-[var(--status-degraded)]">
                    {group.reason}
                  </span>
                  <Pill variant="meta">{`${group.count} resource${group.count === 1 ? "" : "s"}`}</Pill>
                </div>
                {group.remedy ? (
                  <p className="mt-1 text-[13px] text-[var(--foreground-muted)]">{group.remedy}</p>
                ) : (
                  <p className="mt-1 text-[13px] text-[var(--foreground-subtle)]">
                    This panel has no remedy text for this slug. It is still a refusal — read the
                    provider job payload below.
                  </p>
                )}
                {group.sampleDetail ? (
                  <p className="mt-1 font-mono text-[11px] text-[var(--foreground-subtle)]">
                    e.g. {group.sampleDetail}
                    {group.sampleUrl ? ` · ${group.sampleUrl}` : ""}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      <RunMirrorFidelitySection mirror={mirror} />
    </Panel>
  );
}

/**
 * The mirror-fidelity spot check: does what we hold still equal what the issuing
 * source serves?
 *
 * `diverged` means a document we hold may no longer equal its source, and the run
 * discards the whole batch unpublished. `source_unreachable` is a completely
 * different statement — the canton was down, so the check did not run — and must
 * never render as a pass. Nor may an absent block: no check is not a clean check.
 */
function RunMirrorFidelitySection({ mirror }: { mirror: ReturnType<typeof readMirrorFidelity> }) {
  if (!mirror) {
    return (
      <div className="space-y-1" data-testid="run-mirror-fidelity">
        <h3 className="text-[13px] font-semibold text-[var(--foreground)]">Mirror fidelity</h3>
        <p className="text-[13px] text-[var(--foreground-subtle)]">
          No mirror-fidelity check ran on this run, so nothing here proves that what we hold equals
          what the issuing source serves. Not checked — not clean.
        </p>
      </div>
    );
  }

  const unverified = mirror.checks.filter((check) => isUnverifiedMirrorStatus(check.status));

  return (
    <div className="space-y-2" data-testid="run-mirror-fidelity">
      <h3 className="text-[13px] font-semibold text-[var(--foreground)]">Mirror fidelity</h3>
      <div className="flex flex-wrap items-center gap-1.5">
        {mirror.proven ? (
          <Pill level="healthy">proven for the sample</Pill>
        ) : mirror.diverged ? (
          <Pill level="critical">diverged</Pill>
        ) : (
          <Pill level="degraded">not proven</Pill>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Measure label="Sampled" value={mirror.sampled} caption="documents checked" />
        <Measure label="Eligible" value={mirror.candidates} caption="documents checkable" />
        <Measure label="Identical" value={mirror.identical} caption="byte-for-byte" />
        <Measure
          label="Diverged"
          value={mirror.diverged}
          tone={mirror.diverged ? "critical" : "neutral"}
          caption="mirror ≠ source"
        />
        <Measure
          label="Unverified"
          value={mirror.unverified}
          tone={mirror.unverified ? "degraded" : "neutral"}
          caption="check did not run"
        />
      </div>
      {mirror.diverged ? (
        <InlineAlert tone="error">
          The mirror no longer serves bytes identical to the issuing source. The run discards every
          captured document unpublished — the unsampled ones are no more trustworthy than the
          sampled one. This discard does not appear in coverage reconciliation, which runs before
          the capture loop, so the coverage ledger will not reflect it.
        </InlineAlert>
      ) : null}
      {unverified.length > 0 ? (
        <InlineAlert tone="warning">
          {unverified.length} of {mirror.checks.length} check(s) did not run
          {mirror.proven ? "" : " and nothing in this run proved the mirror equals the source"}. An
          unreachable source is not a divergence, and it is not a pass either — the mirror is being
          trusted on assertion for those documents.
        </InlineAlert>
      ) : null}
      {mirror.checks.length > 0 ? (
        <ul className="space-y-1">
          {mirror.checks.map((check) => (
            <li
              key={`${check.status}-${check.sourceUrl ?? check.tolId ?? "unknown"}`}
              className="rounded-[8px] border border-[var(--border-faint)] bg-white/70 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[11px] font-semibold text-[var(--foreground)]">
                  {check.status}
                </span>
                {check.sourceUrl ? (
                  <a
                    href={check.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-[var(--brand)] underline-offset-2 hover:underline"
                  >
                    {check.sourceUrl}
                  </a>
                ) : null}
              </div>
              {check.detail ? (
                <p className="text-[11px] text-[var(--foreground-subtle)]">{check.detail}</p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-[11px] text-[var(--foreground-subtle)]">
        A sample is a sample. Proving one document does not prove the batch.
      </p>
    </div>
  );
}
