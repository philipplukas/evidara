/**
 * `JurisdictionEditV2` — edit counterpart to `JurisdictionCreateV2`, same
 * pattern as `AuthorityEditV2`. `useEditController({ resource, id })`
 * hydrates `<Form record={...}>`; the shared body re-renders with
 * `idDisabled` so the immutable `jurisdiction_id` is visible but not
 * editable.
 */
"use client";

import { Form, useEditController, useNotify } from "ra-core";
import { useNavigate, useParams } from "react-router-dom";
import type { JurisdictionRecord } from "../../lib/admin/dataProvider";
import { Button } from "../../ui/primitives";
import { JurisdictionFormBodyV2 } from "./JurisdictionFormV2";

export default function JurisdictionEditV2() {
  const { id } = useParams();
  const notify = useNotify();
  const navigate = useNavigate();
  const controller = useEditController<JurisdictionRecord>({
    resource: "jurisdictions",
    id,
    mutationMode: "pessimistic",
    mutationOptions: {
      onSuccess: () => {
        notify("Jurisdiction saved", { type: "success" });
        navigate("/jurisdictions");
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : String(error);
        notify(`Could not save: ${message}`, { type: "error" });
      },
    },
  });

  if (controller.isPending) {
    return (
      <div className="px-4 py-10 text-center text-[rgba(29,41,61,0.6)]">Loading jurisdiction…</div>
    );
  }
  if (controller.error || !controller.record) {
    return (
      <div className="px-4 py-10 text-center text-[#b71c1c]">Failed to load jurisdiction.</div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-3xl mx-auto space-y-6">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
          Preview · Tailwind + ra-core · Form path
        </p>
        <h1 className="font-serif text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          Edit {controller.record.name}{" "}
          <span className="text-[rgba(29,41,61,0.5)]">(v2 preview)</span>
        </h1>
        <p className="text-[14px] text-[rgba(29,41,61,0.7)] max-w-[72ch]">
          <code className="font-mono text-[12px]">jurisdiction_id</code> is immutable. On success
          you'll be redirected to the MUI list at{" "}
          <code className="font-mono text-[12px]">/jurisdictions</code>.
        </p>
      </header>

      <Form
        onSubmit={controller.save}
        record={controller.record}
        sanitizeEmptyValues
        warnWhenUnsavedChanges
      >
        <div className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-6">
          <JurisdictionFormBodyV2 idDisabled />

          <footer className="flex items-center justify-end gap-2 pt-2 border-t border-[rgba(29,41,61,0.06)]">
            <Button variant="ghost" onClick={() => navigate("/jurisdictions")} type="button">
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={controller.saving}>
              {controller.saving ? "Saving…" : "Save changes"}
            </Button>
          </footer>
        </div>
      </Form>
    </div>
  );
}
