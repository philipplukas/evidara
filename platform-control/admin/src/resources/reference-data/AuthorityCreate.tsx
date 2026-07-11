/**
 * AuthorityCreate — Tailwind + ra-core authority create form.
 *
 *   - `ra-core`'s `<Form>` provides react-hook-form context to children;
 *     the `<TextInput>` / `<Select>` primitives bind to it via `useInput`.
 *   - `useCreateController({ mutationOptions })` drives the save; the
 *     returned `save` validates, calls `dataProvider.create`, and fires
 *     onSuccess/onError.
 *   - `useNotify()` pushes notifications to the shell's toast surface.
 *
 * After a successful create, we redirect to `/authorities` so the operator
 * can visually confirm the record landed.
 */
"use client";

import { Form, useCreateController, useNotify } from "ra-core";
import { useNavigate } from "react-router-dom";
import type { AuthorityRecord } from "../../lib/admin/dataProvider";
import { Button } from "../../ui/primitives";
import { AuthorityFormBody } from "./AuthorityForm";

// Authorities default to global (nullable jurisdiction_id); the operator can
// scope them to a jurisdiction via the picker in the form body.
const CREATE_DEFAULTS = { jurisdiction_id: null as string | null };

export default function AuthorityCreate() {
  const notify = useNotify();
  const navigate = useNavigate();
  // `useCreateController` returns a `save` function that `<Form onSubmit>`
  // passes validated values into. `mutationOptions` surface the
  // provider-level success/error, not RHF-level — those separations
  // matter: field validation errors are shown inline, server errors fire
  // `onError` below.
  const controller = useCreateController<AuthorityRecord>({
    resource: "authorities",
    mutationOptions: {
      onSuccess: () => {
        notify("Authority created", { type: "success" });
        navigate("/authorities");
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : String(error);
        notify(`Could not create authority: ${message}`, { type: "error" });
      },
    },
  });

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-3xl mx-auto space-y-6">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--text-meta)]">
          Reference data
        </p>
        <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          Create authority
        </h1>
        <p className="text-[14px] text-[var(--text-meta)] max-w-[72ch]">
          Add an authority used by source setup and operator review flows. Leave the jurisdiction
          blank for a global authority, or scope it to one jurisdiction. Successful creation returns
          to the authority list.
        </p>
      </header>

      <Form onSubmit={controller.save} defaultValues={CREATE_DEFAULTS} sanitizeEmptyValues>
        <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-panel)] p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-6">
          <AuthorityFormBody />

          <footer className="flex items-center justify-end gap-2 pt-2 border-t border-[var(--border)]">
            <Button variant="ghost" onClick={() => navigate("/authorities")} type="button">
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={controller.saving}>
              {controller.saving ? "Creating…" : "Create authority"}
            </Button>
          </footer>
        </div>
      </Form>
    </div>
  );
}
