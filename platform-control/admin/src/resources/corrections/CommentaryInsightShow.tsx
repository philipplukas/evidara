/**
 * `CommentaryInsightShow` — detail view + claim editor for a commentary insight
 * (#428), rendered with Tailwind + `ra-core` primitives (ADR-0026).
 *
 * Reads the overlay row via `GET /v1/commentary-insights/{id}`. The editor
 * submits a `field_edit` correction through `useCreate("corrections", ...)`
 * (POST /v1/corrections per PR #440 — corrections are the canonical write
 * surface). Once the server applies the correction (a separate operator step on
 * the Corrections queue), the overlay refreshes via React Query's cache.
 *
 * Per the deviation noted in #440's PR body: there is no PATCH on commentary
 * insights. All edits flow through the corrections audit log so provenance is
 * preserved.
 */
"use client";

import { useCreate, useNotify, useShowController } from "ra-core";
import { useState } from "react";
import { useParams } from "react-router-dom";
import type { CommentaryInsightRaRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { Button, DetailGrid, FieldCell, Pill } from "../../ui/primitives";

const EDITOR_INPUT_CLASS =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--surface-input)] px-3 py-2 " +
  "text-sm text-[var(--foreground)] placeholder:text-[var(--foreground-subtle)] " +
  "shadow-[var(--shadow-inset-surface)] transition-[border-color,box-shadow] " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
  "hover:border-[var(--accent-core)]/30";

function ClaimEditorPanel({ record }: { record: CommentaryInsightRaRecord }) {
  const notify = useNotify();
  const [create, { isLoading }] = useCreate();
  const [draftClaim, setDraftClaim] = useState("");
  const [rationale, setRationale] = useState("");

  const initialClaim = record.claim;
  const claim = draftClaim || initialClaim;
  const dirty = draftClaim !== "" && draftClaim !== initialClaim;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!dirty) {
      notify("No changes to submit", { type: "info" });
      return;
    }
    create(
      "corrections",
      {
        data: {
          target_entity_type: "commentary_insight",
          target_entity_id: record.insight_id,
          correction_type: "field_edit",
          payload: { field: "claim", value: claim },
          original_snapshot: { claim: initialClaim },
          rationale: rationale.trim().length > 0 ? rationale.trim() : undefined,
        },
      },
      {
        onSuccess: () => {
          notify("Correction submitted — pending an operator action on the Corrections queue.", {
            type: "success",
          });
          setDraftClaim("");
          setRationale("");
        },
        onError: (err: unknown) => {
          const message = err instanceof Error ? err.message : "Submit failed";
          notify(message, { type: "error" });
        },
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Edit claim</h2>
        <p className="text-[13px] text-[var(--foreground-subtle)]">
          Submitting writes a <code className="font-mono text-[12px]">field_edit</code> correction.
          The change becomes visible on the overlay once the correction is applied from the
          Corrections queue.
        </p>
      </div>
      <label className="flex flex-col gap-1.5 text-[12px] font-medium text-[var(--foreground-muted)]">
        Claim
        <textarea
          value={claim}
          onChange={(e) => setDraftClaim(e.target.value)}
          rows={3}
          className={EDITOR_INPUT_CLASS}
        />
      </label>
      <label className="flex flex-col gap-1.5 text-[12px] font-medium text-[var(--foreground-muted)]">
        Rationale (optional)
        <input
          type="text"
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          placeholder="Why this edit?"
          className={EDITOR_INPUT_CLASS}
        />
      </label>
      <div>
        <Button type="submit" variant="primary" disabled={!dirty || isLoading}>
          {isLoading ? "Submitting…" : "Submit field edit"}
        </Button>
      </div>
    </form>
  );
}

export function CommentaryInsightShow() {
  const { id } = useParams();
  const controller = useShowController<CommentaryInsightRaRecord>({
    resource: "commentary-insights",
    id,
  });
  const record = controller.record;

  if (controller.isPending) {
    return (
      <div className="px-4 py-10 text-center text-[var(--foreground-subtle)]">Loading insight…</div>
    );
  }
  if (controller.error || !record) {
    return (
      <div className="px-4 py-10 text-center text-[var(--status-critical)]">
        Failed to load commentary insight.
      </div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-6">
      <header className="space-y-3">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
          Commentary insight
        </p>
        <h1 className="font-mono text-[22px] font-semibold text-[var(--foreground)] leading-tight">
          {record.insight_id}
        </h1>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill variant="meta">{`Type: ${record.insight_type}`}</Pill>
          <Pill variant="meta">{`Review: ${record.review_state}`}</Pill>
          <Pill variant="meta">{`Rev: ${record.overlay_revision}`}</Pill>
        </div>
      </header>

      <DetailGrid>
        <FieldCell label="Insight ID">
          <span className="font-mono text-[13px]">{record.insight_id}</span>
        </FieldCell>
        <FieldCell label="Document">
          <span className="font-mono text-[13px]">{record.document_id}</span>
        </FieldCell>
        <FieldCell label="Type">{record.insight_type}</FieldCell>
        <FieldCell label="Review state">{record.review_state}</FieldCell>
        <FieldCell label="Claim" span="full">
          {record.claim}
        </FieldCell>
        <FieldCell label="Source passage" span="full">
          {record.display_text || <span className="text-[var(--foreground-faint)]">—</span>}
        </FieldCell>
        <FieldCell label="Overlay revision">{record.overlay_revision}</FieldCell>
        <FieldCell label="Last correction">
          {record.last_correction_id ? (
            <span className="font-mono text-[13px]">{record.last_correction_id}</span>
          ) : (
            <span className="text-[var(--foreground-faint)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Updated">{formatSwissDateTime(record.updated_at) || "—"}</FieldCell>
      </DetailGrid>

      <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
        <ClaimEditorPanel record={record} />
      </section>
    </div>
  );
}
