/*
 * SPIKE — AuthorityEditV2
 *
 * Paired with AuthorityCreateV2. Proves the edit path:
 *
 *   - `useEditController({ resource, id })` fetches the existing record
 *     and returns `{ record, save, saving }`.
 *   - `<Form record={record}>` seeds react-hook-form `defaultValues` from
 *     the fetched record, so our `<TextField>` inputs show existing
 *     values without any manual wiring.
 *   - The same `<AuthorityFormBodyV2>` renders — no code duplication
 *     between create and edit.
 *
 * Deferred identically to AuthorityCreateV2 (jurisdiction select, scope
 * / slug change alerts). The `authority_id` field is rendered disabled so
 * operators can see the identifier they're editing without being able to
 * change it.
 */
"use client";

import { Form, useEditController, useNotify } from "ra-core";
import { useNavigate, useParams } from "react-router-dom";
import type { AuthorityRecord } from "../../lib/admin/dataProvider";
import { Button } from "../../ui/primitives";
import { AuthorityFormBodyV2 } from "./AuthorityFormV2";

export default function AuthorityEditV2() {
  const { id } = useParams();
  const notify = useNotify();
  const navigate = useNavigate();
  const controller = useEditController<AuthorityRecord>({
    resource: "authorities",
    id,
    mutationMode: "pessimistic",
    mutationOptions: {
      onSuccess: () => {
        notify("Authority saved", { type: "success" });
        navigate("/authorities");
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : String(error);
        notify(`Could not save: ${message}`, { type: "error" });
      },
    },
  });

  if (controller.isPending) {
    return <div className="px-4 py-10 text-center text-[var(--text-meta)]">Loading authority…</div>;
  }
  if (controller.error || !controller.record) {
    return (
      <div className="px-4 py-10 text-center text-[var(--status-critical)]">
        Failed to load authority.
      </div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-3xl mx-auto space-y-6">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--text-meta)]">
          Reference data
        </p>
        <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          Edit {controller.record.name}
        </h1>
        <p className="text-[14px] text-[var(--text-meta)] max-w-[72ch]">
          Update the authority display name and slug. The authority ID remains immutable for linked
          records.
        </p>
      </header>

      <Form
        onSubmit={controller.save}
        record={controller.record}
        sanitizeEmptyValues
        warnWhenUnsavedChanges
      >
        <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-panel)] p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-6">
          <AuthorityFormBodyV2 idDisabled />

          <footer className="flex items-center justify-end gap-2 pt-2 border-t border-[var(--border)]">
            <Button variant="ghost" onClick={() => navigate("/authorities")} type="button">
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
