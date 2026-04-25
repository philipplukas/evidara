/**
 * `CommentaryInsightEdit` — operator field-edit form for a commentary
 * insight. Loads the current overlay through `useShowController`, lets
 * the operator edit the whitelisted patchable fields (`claim`,
 * `display_text`, `review_state`), and submits via the dedicated
 * `controlPlaneActions.applyCommentaryInsightFieldEdit` action — not
 * through `dataProvider.update`, since the platform-control PATCH expects
 * the correction envelope (`payload` + `original_snapshot` +
 * `rationale`).
 *
 * On success: refresh the controller (so the next visit reflects the
 * overlay), pop a toast, and stay on the same page so the operator can
 * see the diff land in the history strip.
 */
"use client";

import { useNotify, useRefresh, useShowController } from "ra-core";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ResourceName } from "../../domain/resourceNames";
import {
  type ApplyCommentaryInsightFieldEditResult,
  type CommentaryInsightRecord,
  type CorrectionRecord,
  controlPlaneActions,
} from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { Button, DetailGrid, FieldCell, Pill } from "../../ui/primitives";
import {
  buildCorrectionDiff,
  buildFieldEditEnvelope,
  draftFromInsight,
  type FieldEditDraft,
  formatDiffValue,
  REVIEW_STATE_LABEL,
  REVIEW_STATE_VALUES,
  reviewStateToLevel,
  sortCorrectionsNewestFirst,
  validateFieldEditDraft,
} from "./commentaryInsight";

function HistoryStrip({ corrections }: { corrections: CorrectionRecord[] }) {
  const ordered = sortCorrectionsNewestFirst(corrections);
  if (ordered.length === 0) {
    return (
      <p className="text-[13px] text-[rgba(29,41,61,0.6)]">
        No corrections yet — this insight is still in its machine-generated form.
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {ordered.map((correction) => {
        const diff = buildCorrectionDiff(correction);
        return (
          <li
            key={correction.correction_id}
            className="rounded-[14px] border border-[rgba(29,41,61,0.08)] bg-white/70 p-4"
          >
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <Pill variant="meta">{correction.correction_type}</Pill>
              <Pill variant="meta">{correction.status}</Pill>
              <span className="font-mono text-[11px] text-[rgba(29,41,61,0.55)]">
                {correction.correction_id}
              </span>
              <span className="text-[12px] text-[rgba(29,41,61,0.7)] ml-auto">
                {formatSwissDateTime(correction.applied_at ?? correction.created_at)} ·{" "}
                {correction.operator_id}
              </span>
            </div>
            {correction.rationale ? (
              <p className="text-[13px] text-[rgba(29,41,61,0.85)] italic mb-2">
                “{correction.rationale}”
              </p>
            ) : null}
            {diff.length > 0 ? (
              <table className="w-full text-[12px] border-collapse">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-[0.06em] text-[rgba(29,41,61,0.6)]">
                    <th className="py-1 pr-3 font-semibold">Field</th>
                    <th className="py-1 pr-3 font-semibold">Before</th>
                    <th className="py-1 font-semibold">After</th>
                  </tr>
                </thead>
                <tbody>
                  {diff.map((entry) => (
                    <tr key={entry.field} className="border-t border-[rgba(29,41,61,0.06)]">
                      <td className="py-1.5 pr-3 font-mono text-[12px]">{entry.field}</td>
                      <td className="py-1.5 pr-3 whitespace-pre-wrap text-[rgba(29,41,61,0.7)]">
                        {formatDiffValue(entry.before)}
                      </td>
                      <td className="py-1.5 whitespace-pre-wrap text-[var(--foreground)]">
                        {formatDiffValue(entry.after)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export default function CommentaryInsightEdit() {
  const { id } = useParams();
  const navigate = useNavigate();
  const notify = useNotify();
  const refresh = useRefresh();

  const controller = useShowController<CommentaryInsightRecord>({
    resource: ResourceName.CommentaryInsights,
    id,
  });
  const insight = controller.record;

  const [draft, setDraft] = useState<FieldEditDraft | null>(null);
  const [errors, setErrors] = useState<
    Partial<Record<keyof FieldEditDraft, string>> & { _form?: string }
  >({});
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<CorrectionRecord[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Seed the draft once the record arrives and reseed if the operator
  // navigates between insights without unmounting (rare, but possible
  // when react-router keeps the component alive).
  useEffect(() => {
    if (insight) {
      setDraft(draftFromInsight(insight));
    }
  }, [insight]);

  useEffect(() => {
    let cancelled = false;
    if (!insight?.insight_id) return;
    setHistory(null);
    setHistoryError(null);
    controlPlaneActions
      .getCommentaryInsightHistory(insight.insight_id)
      .then((rows) => {
        if (!cancelled) setHistory(rows);
      })
      .catch((error) => {
        if (cancelled) return;
        setHistoryError(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
    };
  }, [insight?.insight_id]);

  if (controller.isPending || !insight || !draft) {
    return (
      <div className="px-4 py-10 text-center text-[rgba(29,41,61,0.6)]">
        Loading commentary insight…
      </div>
    );
  }
  if (controller.error) {
    return (
      <div className="px-4 py-10 text-center text-[#b71c1c]">
        Failed to load commentary insight.
      </div>
    );
  }

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const validation = validateFieldEditDraft(draft);
    if (!validation.ok) {
      setErrors(validation.errors);
      return;
    }
    const envelope = buildFieldEditEnvelope(insight, draft);
    if (!envelope.hasChanges) {
      setErrors({ _form: "No fields changed — nothing to submit." });
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      const result: ApplyCommentaryInsightFieldEditResult =
        await controlPlaneActions.applyCommentaryInsightFieldEdit({
          insightId: insight.insight_id,
          payload: envelope.payload,
          original_snapshot: envelope.original_snapshot,
          rationale: draft.rationale.trim(),
        });
      notify("Commentary insight edit recorded.", { type: "success" });
      // Reseed the draft from the post-overlay record so subsequent
      // edits diff against the new baseline.
      setDraft(draftFromInsight(result.insight));
      // Optimistically prepend the new correction so the operator sees
      // their edit land before the network round-trip completes — the
      // refresh below reconciles with the canonical server state.
      setHistory((prev) => [result.correction, ...(prev ?? [])]);
      refresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      notify(`Could not record edit: ${message}`, { type: "error" });
      setErrors({ _form: message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
          Commentary insights · Edit
        </p>
        <h1 className="font-serif text-[26px] font-semibold text-[var(--foreground)] leading-tight">
          {insight.claim}
        </h1>
        <div className="font-mono text-[12px] text-[rgba(29,41,61,0.6)]">{insight.insight_id}</div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill level={reviewStateToLevel(insight.review_state)}>
            {REVIEW_STATE_LABEL[insight.review_state]}
          </Pill>
          <Pill variant="meta">{insight.insight_type}</Pill>
          <Pill variant="meta">{`Confidence ${insight.confidence.toFixed(2)}`}</Pill>
          {insight.last_correction_id ? (
            <Link
              to={`/${ResourceName.Corrections}`}
              className="font-mono text-[11px] text-[var(--brand)] hover:underline"
            >
              Last correction: {insight.last_correction_id}
            </Link>
          ) : null}
        </div>
      </header>

      <DetailGrid>
        <FieldCell label="Document">
          <span className="font-mono text-[12px]">{insight.document_id}</span>
        </FieldCell>
        <FieldCell label="Document revision">{insight.document_revision}</FieldCell>
        <FieldCell label="Processing manifest">
          <span className="font-mono text-[12px]">{insight.processing_manifest_id}</span>
        </FieldCell>
        <FieldCell label="Generator">
          {insight.generator.name}{" "}
          <span className="text-[rgba(29,41,61,0.55)]">v{insight.generator.version}</span>
        </FieldCell>
      </DetailGrid>

      <section className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-4">
        <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Apply field edit</h2>
        <p className="text-[13px] text-[rgba(29,41,61,0.65)]">
          Submitting writes a `field_edit` correction (see ADR-0011) and updates the operator
          overlay. The DI output is never mutated.
        </p>

        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.7)]">
            Claim
          </span>
          <textarea
            value={draft.claim}
            rows={2}
            onChange={(event) => setDraft({ ...draft, claim: event.target.value })}
            aria-invalid={!!errors.claim}
            className="rounded-xl border border-[rgba(29,41,61,0.16)] bg-white/85 px-3 py-2.5 text-sm text-[var(--foreground)] hover:border-[rgba(29,41,61,0.28)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)] resize-y"
          />
          {errors.claim ? <span className="text-[12px] text-[#b71c1c]">{errors.claim}</span> : null}
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.7)]">
            Display text
          </span>
          <textarea
            value={draft.display_text}
            rows={4}
            onChange={(event) => setDraft({ ...draft, display_text: event.target.value })}
            aria-invalid={!!errors.display_text}
            className="rounded-xl border border-[rgba(29,41,61,0.16)] bg-white/85 px-3 py-2.5 text-sm text-[var(--foreground)] hover:border-[rgba(29,41,61,0.28)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)] resize-y"
          />
          {errors.display_text ? (
            <span className="text-[12px] text-[#b71c1c]">{errors.display_text}</span>
          ) : null}
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.7)]">
            Review state
          </span>
          <select
            value={draft.review_state}
            onChange={(event) =>
              setDraft({
                ...draft,
                review_state: event.target.value as FieldEditDraft["review_state"],
              })
            }
            className="rounded-xl border border-[rgba(29,41,61,0.16)] bg-white/85 px-3 py-2.5 text-sm text-[var(--foreground)] hover:border-[rgba(29,41,61,0.28)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)]"
          >
            {REVIEW_STATE_VALUES.map((state) => (
              <option key={state} value={state}>
                {REVIEW_STATE_LABEL[state]}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[rgba(29,41,61,0.7)]">
            Rationale
            <span aria-hidden className="text-[#b71c1c] ml-1">
              *
            </span>
          </span>
          <textarea
            value={draft.rationale}
            rows={3}
            placeholder="Why is this edit being applied?"
            onChange={(event) => setDraft({ ...draft, rationale: event.target.value })}
            aria-invalid={!!errors.rationale}
            className="rounded-xl border border-[rgba(29,41,61,0.16)] bg-white/85 px-3 py-2.5 text-sm text-[var(--foreground)] hover:border-[rgba(29,41,61,0.28)] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-focus-ring)] resize-y"
          />
          {errors.rationale ? (
            <span className="text-[12px] text-[#b71c1c]">{errors.rationale}</span>
          ) : null}
        </label>

        {errors._form ? (
          <p className="text-[13px] text-[#b71c1c] font-medium">{errors._form}</p>
        ) : null}

        <footer className="flex items-center justify-end gap-2 pt-2 border-t border-[rgba(29,41,61,0.06)]">
          <Button
            type="button"
            variant="ghost"
            onClick={() => navigate(`/${ResourceName.CommentaryInsights}`)}
          >
            Back to list
          </Button>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? "Submitting…" : "Submit field edit"}
          </Button>
        </footer>
      </section>

      <section className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-3">
        <header className="flex items-baseline justify-between">
          <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Correction history</h2>
          <Link
            to={`/${ResourceName.CommentaryInsights}/${encodeURIComponent(
              insight.insight_id,
            )}/history`}
            className="text-[12px] text-[var(--brand)] hover:underline"
          >
            Open full history
          </Link>
        </header>
        {historyError ? (
          <p className="text-[13px] text-[#b71c1c]">Could not load history: {historyError}</p>
        ) : history === null ? (
          <p className="text-[13px] text-[rgba(29,41,61,0.6)]">Loading history…</p>
        ) : (
          <HistoryStrip corrections={history} />
        )}
      </section>
    </form>
  );
}
