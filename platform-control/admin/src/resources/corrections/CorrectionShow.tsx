/**
 * `CorrectionShow` — detail view for a single correction (#428), rendered with
 * Tailwind + `ra-core` primitives (ADR-0026).
 *
 * Surfaces the audit-log envelope plus the lifecycle-action buttons. The action
 * buttons call `useUpdate("corrections", { id, data: { status } })` which
 * dispatches to `PATCH /v1/corrections/{id}` (PR #440 — server enforces legal
 * transitions; illegal transitions return 409). The record's current status
 * drives which actions are available.
 */
"use client";

import { useNotify, useShowController, useUpdate } from "ra-core";
import { useState } from "react";
import { useParams } from "react-router-dom";
import type { CorrectionRecord } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { Button, DetailGrid, FieldCell, Pill, type PillLevel } from "../../ui/primitives";

const TERMINAL_STATUSES = new Set<CorrectionRecord["status"]>(["rejected", "superseded"]);

const STATUS_LEVEL: Record<CorrectionRecord["status"], PillLevel> = {
  pending: "degraded",
  applied: "healthy",
  rejected: "critical",
  superseded: "neutral",
};

type CorrectionTransition = "applied" | "rejected" | "superseded";

const TRANSITION_LABEL: Record<CorrectionTransition, string> = {
  applied: "Apply",
  rejected: "Reject",
  superseded: "Mark superseded",
};

/**
 * Corrections state machine (PR #440), mirrored client-side so the detail page
 * only offers legal transitions:
 *   pending  → applied | rejected
 *   applied  → superseded
 *   rejected / superseded → (terminal)
 * The server remains the source of truth — illegal transitions still 409.
 */
export function correctionTransitions(status: CorrectionRecord["status"]): CorrectionTransition[] {
  if (status === "pending") return ["applied", "rejected"];
  if (status === "applied") return ["superseded"];
  return [];
}

function CorrectionLifecycleActions({ record }: { record: CorrectionRecord }) {
  const notify = useNotify();
  const [update, { isLoading }] = useUpdate();
  const [pending, setPending] = useState<CorrectionTransition | null>(null);

  if (TERMINAL_STATUSES.has(record.status)) {
    return (
      <p className="text-sm text-[var(--foreground-subtle)]">
        Correction is {record.status} — no further transitions available.
      </p>
    );
  }

  const handle = (next: CorrectionTransition) => {
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

  const allow = correctionTransitions(record.status);

  return (
    <div className="flex flex-wrap gap-2">
      {allow.map((next) => (
        <Button
          key={next}
          type="button"
          variant={next === "applied" ? "primary" : "secondary"}
          disabled={isLoading && pending === next}
          onClick={() => handle(next)}
        >
          {TRANSITION_LABEL[next]}
        </Button>
      ))}
    </div>
  );
}

export function CorrectionShow() {
  const { id } = useParams();
  const controller = useShowController<CorrectionRecord>({ resource: "corrections", id });
  const record = controller.record;

  if (controller.isPending) {
    return (
      <div className="px-4 py-10 text-center text-[var(--foreground-subtle)]">
        Loading correction…
      </div>
    );
  }
  if (controller.error || !record) {
    return (
      <div className="px-4 py-10 text-center text-[var(--status-critical)]">
        Failed to load correction.
      </div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-6">
      <header className="space-y-3">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
          Correction detail
        </p>
        <h1 className="font-mono text-[22px] font-semibold text-[var(--foreground)] leading-tight">
          {record.correction_id}
        </h1>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill level={STATUS_LEVEL[record.status]}>{record.status}</Pill>
          <Pill variant="meta">{`Type: ${record.correction_type}`}</Pill>
          <Pill variant="meta">{`Target: ${record.target_entity_type}`}</Pill>
        </div>
      </header>

      <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-3">
        <div className="space-y-1">
          <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Lifecycle actions</h2>
          <p className="text-[13px] text-[var(--foreground-subtle)]">
            The server enforces legal transitions — pending corrections can be applied or rejected;
            applied corrections can be superseded.
          </p>
        </div>
        <CorrectionLifecycleActions record={record} />
      </section>

      <DetailGrid>
        <FieldCell label="Correction ID">
          <span className="font-mono text-[13px]">{record.correction_id}</span>
        </FieldCell>
        <FieldCell label="Status">{record.status}</FieldCell>
        <FieldCell label="Type">{record.correction_type}</FieldCell>
        <FieldCell label="Target type">{record.target_entity_type}</FieldCell>
        <FieldCell label="Target ID">
          <span className="font-mono text-[13px]">{record.target_entity_id}</span>
        </FieldCell>
        <FieldCell label="Operator">
          {record.operator_id || <span className="text-[var(--foreground-faint)]">—</span>}
        </FieldCell>
        <FieldCell label="Rationale" span="full">
          {record.rationale ?? <span className="text-[var(--foreground-faint)]">—</span>}
        </FieldCell>
        <FieldCell label="Created">{formatSwissDateTime(record.created_at) || "—"}</FieldCell>
        <FieldCell label="Applied">{formatSwissDateTime(record.applied_at) || "—"}</FieldCell>
      </DetailGrid>
    </div>
  );
}
