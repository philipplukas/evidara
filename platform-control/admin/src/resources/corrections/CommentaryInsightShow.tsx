"use client";

/**
 * Detail view + claim editor for a commentary insight (#428).
 *
 * Reads the overlay row via `GET /v1/commentary-insights/{id}`. The
 * editor submits a `field_edit` correction through
 * `dataProvider.create("corrections", ...)` (POST /v1/corrections per
 * PR #440 — corrections are the canonical write surface). Once the
 * server applies the correction (separate operator step on the
 * Corrections queue), the overlay refreshes via React Admin's cache.
 *
 * Per the deviation noted in #440's PR body: there is no PATCH on
 * commentary insights. All edits flow through the corrections audit
 * log so provenance is preserved.
 */

import { useState } from "react";
import {
  Show,
  SimpleShowLayout,
  TextField,
  useCreate,
  useNotify,
  useRecordContext,
} from "react-admin";
import { SwissDateField } from "../../components/SwissDateField";
import type { CommentaryInsightRecord } from "../../lib/admin/dataProvider";

function ClaimEditorPanel() {
  const record = useRecordContext<CommentaryInsightRecord>();
  const notify = useNotify();
  const [create, { isLoading }] = useCreate();
  const [draftClaim, setDraftClaim] = useState("");
  const [rationale, setRationale] = useState("");

  if (!record) return null;

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
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 pt-3">
      <h3 className="text-sm font-semibold text-foreground">Edit claim</h3>
      <p className="text-xs text-muted-foreground">
        Submitting writes a <code>field_edit</code> correction. The change becomes visible on the
        overlay once the correction is applied from the Corrections queue.
      </p>
      <label className="flex flex-col gap-1 text-xs font-medium">
        Claim
        <textarea
          value={claim}
          onChange={(e) => setDraftClaim(e.target.value)}
          rows={3}
          className="rounded-md border border-border/70 bg-background px-2 py-1.5 text-sm text-foreground"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs font-medium">
        Rationale (optional)
        <input
          type="text"
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          placeholder="Why this edit?"
          className="rounded-md border border-border/70 bg-background px-2 py-1.5 text-sm text-foreground"
        />
      </label>
      <div>
        <button
          type="submit"
          disabled={!dirty || isLoading}
          className="rounded-md border border-border/70 bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:border-accent-core/40 hover:bg-accent-core/5 disabled:opacity-50"
        >
          {isLoading ? "Submitting…" : "Submit field edit"}
        </button>
      </div>
    </form>
  );
}

export function CommentaryInsightShow() {
  return (
    <Show title="Commentary insight">
      <SimpleShowLayout>
        <TextField source="insight_id" label="Insight ID" />
        <TextField source="document_id" label="Document" />
        <TextField source="insight_type" label="Type" />
        <TextField source="claim" label="Claim" />
        <TextField source="display_text" label="Source passage" />
        <TextField source="review_state" label="Review state" />
        <TextField source="overlay_revision" label="Overlay revision" />
        <TextField source="last_correction_id" label="Last correction" />
        <SwissDateField source="updated_at" label="Updated" showTime />
        <ClaimEditorPanel />
      </SimpleShowLayout>
    </Show>
  );
}
