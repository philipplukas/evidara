/**
 * `CommentaryInsightHistory` — full-page correction trail for an
 * insight. Mirrors the strip embedded in `CommentaryInsightEdit` but
 * stays focused on read-only audit; useful when an operator needs the
 * URL to share or to scroll through a long correction tail.
 */
"use client";

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ResourceName } from "../../domain/resourceNames";
import { type CorrectionRecord, controlPlaneActions } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { Pill } from "../../ui/primitives";
import {
  buildCorrectionDiff,
  formatDiffValue,
  sortCorrectionsNewestFirst,
} from "./commentaryInsight";

export default function CommentaryInsightHistory() {
  const { id } = useParams();
  const [history, setHistory] = useState<CorrectionRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!id) return;
    setHistory(null);
    setError(null);
    controlPlaneActions
      .getCommentaryInsightHistory(id)
      .then((rows) => {
        if (!cancelled) setHistory(rows);
      })
      .catch((failure) => {
        if (cancelled) return;
        setError(failure instanceof Error ? failure.message : String(failure));
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
          Commentary insights · History
        </p>
        <h1 className="font-serif text-[26px] font-semibold text-[var(--foreground)] leading-tight">
          Correction trail
        </h1>
        <div className="font-mono text-[12px] text-[rgba(29,41,61,0.6)]">{id}</div>
        <Link
          to={`/${ResourceName.CommentaryInsights}/${encodeURIComponent(String(id ?? ""))}`}
          className="text-[13px] text-[var(--brand)] hover:underline"
        >
          ← Back to editor
        </Link>
      </header>

      {error ? (
        <div className="rounded-[18px] border border-[rgba(198,40,40,0.4)] bg-[rgba(198,40,40,0.06)] p-5 text-[#b71c1c]">
          Could not load correction history: {error}
        </div>
      ) : history === null ? (
        <div className="px-4 py-10 text-center text-[rgba(29,41,61,0.6)]">Loading history…</div>
      ) : history.length === 0 ? (
        <div className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-6 text-[14px] text-[rgba(29,41,61,0.7)] shadow-[var(--shadow-card)] backdrop-blur-[12px]">
          No corrections recorded for this insight yet.
        </div>
      ) : (
        <ul className="space-y-3">
          {sortCorrectionsNewestFirst(history).map((correction) => {
            const diff = buildCorrectionDiff(correction);
            return (
              <li
                key={correction.correction_id}
                className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 shadow-[var(--shadow-card)] backdrop-blur-[12px]"
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
      )}
    </div>
  );
}
