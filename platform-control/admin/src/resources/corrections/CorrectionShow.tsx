"use client";

/**
 * Detail view for a single correction (#428).
 *
 * Surfaces the audit-log envelope plus the lifecycle-action buttons.
 * The action buttons call `dataProvider.update("corrections", { id, data: { status } })`
 * which dispatches to `PATCH /v1/corrections/{id}` (PR #440 — server
 * enforces legal transitions; illegal transitions return 409). The
 * record's current status drives which actions are available.
 */

import { useState } from "react";
import {
  Show,
  SimpleShowLayout,
  TextField,
  useNotify,
  useRecordContext,
  useUpdate,
} from "react-admin";
import { SwissDateField } from "../../components/SwissDateField";
import type { CorrectionRecord } from "../../lib/admin/dataProvider";

const TERMINAL_STATUSES = new Set(["rejected", "superseded"]);

function CorrectionLifecycleActions() {
  const record = useRecordContext<CorrectionRecord>();
  const notify = useNotify();
  const [update, { isLoading }] = useUpdate();
  const [pending, setPending] = useState<string | null>(null);

  if (!record) return null;
  if (TERMINAL_STATUSES.has(record.status)) {
    return (
      <p className="text-sm text-muted-foreground">
        Correction is {record.status} — no further transitions available.
      </p>
    );
  }

  const handle = (next: "applied" | "rejected" | "superseded") => {
    setPending(next);
    update(
      "corrections",
      { id: record.correction_id, data: { status: next }, previousData: record },
      {
        onSuccess: () => notify(`Correction ${next}`, { type: "success" }),
        onError: (err: unknown) => {
          const message = err instanceof Error ? err.message : "Update failed";
          notify(message, { type: "error" });
        },
        onSettled: () => setPending(null),
      },
    );
  };

  // Legal transitions per PR #440 / corrections state machine:
  //   pending  → applied | rejected
  //   applied  → superseded
  const allow: Array<"applied" | "rejected" | "superseded"> =
    record.status === "pending"
      ? ["applied", "rejected"]
      : record.status === "applied"
        ? ["superseded"]
        : [];

  return (
    <div className="flex flex-wrap gap-2">
      {allow.map((next) => (
        <button
          key={next}
          type="button"
          disabled={isLoading && pending === next}
          onClick={() => handle(next)}
          className="rounded-md border border-border/70 bg-background px-3 py-1.5 text-sm font-medium text-foreground shadow-sm hover:border-accent-core/40 hover:bg-accent-core/5 disabled:opacity-50"
        >
          {next === "applied" ? "Apply" : next === "rejected" ? "Reject" : "Mark superseded"}
        </button>
      ))}
    </div>
  );
}

export function CorrectionShow() {
  return (
    <Show title="Correction">
      <SimpleShowLayout>
        <TextField source="correction_id" label="Correction ID" />
        <TextField source="status" label="Status" />
        <TextField source="correction_type" label="Type" />
        <TextField source="target_entity_type" label="Target type" />
        <TextField source="target_entity_id" label="Target ID" />
        <TextField source="operator_id" label="Operator" />
        <TextField source="rationale" label="Rationale" />
        <SwissDateField source="created_at" label="Created" showTime />
        <SwissDateField source="applied_at" label="Applied" showTime />
        <CorrectionLifecycleActions />
      </SimpleShowLayout>
    </Show>
  );
}
