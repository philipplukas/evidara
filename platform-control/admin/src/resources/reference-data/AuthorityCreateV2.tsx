/*
 * SPIKE — AuthorityCreateV2
 *
 * Third reference port — the form path. This is the *actual* migration
 * risk: lists and detail were read-only. Here we validate:
 *
 *   - `ra-core`'s `<Form>` provides react-hook-form context to children.
 *   - `useInput` inside our `<TextField>` primitive binds to that context
 *     (validation, dirty, submit blocking all work without MUI).
 *   - `useCreateController({ mutationOptions })` drives the save; the
 *     `save` function returned is a react-hook-form-shaped submit handler
 *     that validates, calls `dataProvider.create`, and fires
 *     onSuccess/onError.
 *   - `useNotify()` pushes notifications to the `NotificationContext`
 *     (which `<Admin>` provides); until the shell ports, the MUI
 *     `<Notification>` in the outer `<Layout>` still renders them — that's
 *     the intended coexistence pattern during the migration.
 *
 * After a successful create, we redirect to `/authorities` (MUI list) so
 * the operator can visually confirm the record landed. When the list
 * itself ports, this redirect becomes `/authorities-v2`.
 */
"use client";

import { Form, useCreateController, useNotify } from "ra-core";
import { useNavigate } from "react-router-dom";
import type { AuthorityRecord } from "../../lib/admin/dataProvider";
import { Button } from "../../ui/primitives";
import { AuthorityFormBodyV2 } from "./AuthorityFormV2";

// Jurisdiction field is deferred; every created authority is global
// (nullable jurisdiction_id) until the Select primitive ports.
const CREATE_DEFAULTS = { jurisdiction_id: null as string | null };

export default function AuthorityCreateV2() {
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
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
          Preview · Tailwind + ra-core · Form path
        </p>
        <h1 className="font-serif text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          Create authority <span className="text-[rgba(29,41,61,0.5)]">(v2 preview)</span>
        </h1>
        <p className="text-[14px] text-[rgba(29,41,61,0.7)] max-w-[72ch]">
          Jurisdiction select, scope-change alert, and slug-change alert are deferred — see the
          header comment of <code className="font-mono text-[12px]">AuthorityFormV2.tsx</code>.
          Every authority created here is saved as a global (null jurisdiction) authority. On
          success you'll be redirected to the MUI list at{" "}
          <code className="font-mono text-[12px]">/authorities</code>.
        </p>
      </header>

      <Form onSubmit={controller.save} defaultValues={CREATE_DEFAULTS} sanitizeEmptyValues>
        <div className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-6">
          <AuthorityFormBodyV2 />

          <footer className="flex items-center justify-end gap-2 pt-2 border-t border-[rgba(29,41,61,0.06)]">
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
