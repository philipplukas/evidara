"use client";

/**
 * `StageTimeline` — what document-intelligence actually did to one document.
 *
 * Until #903 a document's whole journey through the pipeline was visible as
 * three status transitions, so "where did the time go" and "which stage dropped
 * it" had no answer on any operator surface. This renders the per-stage ledger
 * that `document.processed` now carries.
 *
 * The honesty rules it is written against (OPERATOR_JOBS.md, and the same ones
 * `RunEvidencePanels` follows):
 *
 * - **A missing ledger renders as a stated absence, never as an empty timeline.**
 *   `stages === null` means document-intelligence recorded nothing — an event
 *   from before #903, or a producer that emits none. Drawing six empty rows
 *   would claim the pipeline ran and did nothing.
 * - **A missing count renders as a dash, never as `0`.** `items_in`/`items_out`
 *   are absent when the stage did not measure them. `0 → 0` is a claim about the
 *   work; a dash is the absence of one.
 * - **No ratios and no progress bars.** The bar here is proportional to measured
 *   duration only, and it is decoration on a number that is also printed.
 *
 * What it deliberately does NOT say: what a stage *removed* from the text —
 * excluded footnote apparatus, stripped page furniture, a lifted Randtitel, a
 * dropped citation. That is ADR-0044, it is not implemented, and the caption
 * says so rather than letting silence read as "nothing was removed".
 */

import type { components } from "../../lib/api/generated/platform-control";

type PipelineStage = components["schemas"]["PipelineStage"];

/** Execution order. The wire enum is closed, but ordering is ours to assert. */
const STAGE_ORDER: PipelineStage["name"][] = [
  "normalize",
  "sectionize",
  "extract",
  "assemble",
  "enrich",
  "finalize",
];

const STAGE_LABEL: Record<PipelineStage["name"], string> = {
  normalize: "Normalize",
  sectionize: "Sectionize",
  extract: "Extract",
  assemble: "Assemble",
  enrich: "Enrich",
  finalize: "Finalize",
};

/** Sort by execution order; unknown names keep their position at the end. */
export function orderStages(stages: PipelineStage[]): PipelineStage[] {
  return [...stages].sort((a, b) => {
    const ai = STAGE_ORDER.indexOf(a.name);
    const bi = STAGE_ORDER.indexOf(b.name);
    return (ai === -1 ? STAGE_ORDER.length : ai) - (bi === -1 ? STAGE_ORDER.length : bi);
  });
}

/** A count, or an em dash when the stage did not measure it. Never `0` for absent. */
export function formatCount(value: number | null | undefined): string {
  return typeof value === "number" ? String(value) : "—";
}

/**
 * Microseconds, rendered in the unit a human reads at that magnitude.
 *
 * The wire carries microseconds because milliseconds could not express this
 * pipeline's own timings — every stage of a small HTML document measured `0 ms`,
 * which reads as "nothing was measured" rather than "fast". So the number is
 * never rounded away here either: below a millisecond it stays in µs.
 *
 * A genuine `0 µs` is possible (a stage faster than the clock's resolution) and
 * renders as `0 µs` — a measured zero, distinct from the dash that marks an
 * absent count.
 */
export function formatDuration(us: number): string {
  if (us < 1_000) return `${us} µs`;
  if (us < 1_000_000) {
    const ms = us / 1_000;
    // One decimal below 10 ms, where the fraction still carries signal.
    return `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`;
  }
  return `${(us / 1_000_000).toFixed(2)} s`;
}

export function totalDurationUs(stages: PipelineStage[]): number {
  return stages.reduce((sum, stage) => sum + (stage.duration_us ?? 0), 0);
}

export function StageTimeline({ stages }: { stages: PipelineStage[] | null | undefined }) {
  // `null`/`undefined` is "not recorded" and must not be drawn as an empty
  // timeline. `[]` reaches here only if a producer ever sends one; it is
  // reported as the claim it is, separately from absence.
  if (stages == null) {
    return (
      <p className="text-[13px] text-[var(--text-meta)] m-0">
        No stage timings recorded for this document. Its processing predates stage recording, or the
        producer emits none — this is <em>not</em> a report that the pipeline did no work.
      </p>
    );
  }

  if (stages.length === 0) {
    return (
      <p className="text-[13px] text-[var(--text-meta)] m-0">
        document-intelligence reported an empty stage ledger for this document.
      </p>
    );
  }

  const ordered = orderStages(stages);
  const total = totalDurationUs(ordered);
  const widest = Math.max(...ordered.map((stage) => stage.duration_us ?? 0), 1);

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr>
              {["Stage", "Duration", "In", "Out", ""].map((heading) => (
                <th
                  key={heading}
                  scope="col"
                  className="text-left font-semibold text-[12px] uppercase tracking-[0.06em] text-[var(--text-meta)] py-2 pr-4 whitespace-nowrap"
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ordered.map((stage) => (
              <tr key={stage.name} className="border-t border-[var(--border)]">
                <th
                  scope="row"
                  className="text-left font-semibold py-2 pr-4 whitespace-nowrap text-[var(--foreground)]"
                >
                  {STAGE_LABEL[stage.name] ?? stage.name}
                  {stage.failed ? (
                    <span className="ml-2 text-[12px] font-semibold text-[var(--danger,#b42318)]">
                      failed{stage.error_type ? ` · ${stage.error_type}` : ""}
                    </span>
                  ) : null}
                </th>
                <td className="py-2 pr-4 tabular-nums whitespace-nowrap">
                  {formatDuration(stage.duration_us)}
                </td>
                <td className="py-2 pr-4 tabular-nums">{formatCount(stage.items_in)}</td>
                <td className="py-2 pr-4 tabular-nums">{formatCount(stage.items_out)}</td>
                <td className="py-2 w-[38%] min-w-[120px]">
                  {/* Decoration on a number already printed to its left — not a
                      progress bar, and it encodes nothing the table does not. */}
                  <span
                    aria-hidden
                    className="block h-[6px] rounded-full bg-[var(--accent-core)]"
                    style={{
                      width: `${Math.max(2, ((stage.duration_us ?? 0) / widest) * 100)}%`,
                      opacity: stage.failed ? 0.4 : 1,
                    }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 mb-0 text-[13px] text-[var(--text-meta)]">
        {ordered.length} stages · {formatDuration(total)} measured. Timings and counts only — this
        does not report what a stage removed from the text (excluded footnotes, stripped page
        furniture, a lifted Randtitel, a dropped citation). That disclosure is not implemented, so
        its absence here is not evidence that nothing was removed.
      </p>
    </div>
  );
}
