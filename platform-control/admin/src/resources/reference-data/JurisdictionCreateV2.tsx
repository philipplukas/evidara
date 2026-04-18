/**
 * `JurisdictionCreateV2` — paired with `AuthorityCreateV2`. Same form-path
 * pattern: `useCreateController` + `<Form>` + `useNotify`. Because
 * jurisdictions don't have their own scope selection, the body is simpler
 * than the authority form (name + slug only).
 */
"use client";

import { Form, useCreateController, useNotify } from "ra-core";
import { useNavigate } from "react-router-dom";
import type { JurisdictionRecord } from "../../lib/admin/dataProvider";
import { Button } from "../../ui/primitives";
import { JurisdictionFormBodyV2 } from "./JurisdictionFormV2";

export default function JurisdictionCreateV2() {
  const notify = useNotify();
  const navigate = useNavigate();
  const controller = useCreateController<JurisdictionRecord>({
    resource: "jurisdictions",
    mutationOptions: {
      onSuccess: () => {
        notify("Jurisdiction created", { type: "success" });
        navigate("/jurisdictions");
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : String(error);
        notify(`Could not create jurisdiction: ${message}`, { type: "error" });
      },
    },
  });

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-3xl mx-auto space-y-6">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
          Preview · Tailwind + ra-core · Form path
        </p>
        <h1 className="font-serif text-[28px] font-semibold text-[#1d293d] leading-tight">
          Create jurisdiction <span className="text-[rgba(29,41,61,0.5)]">(v2 preview)</span>
        </h1>
        <p className="text-[14px] text-[rgba(29,41,61,0.7)] max-w-[72ch]">
          Slug-change alert is deferred (pure presentational; ports next). On success you'll be
          redirected to the MUI list at{" "}
          <code className="font-mono text-[12px]">/jurisdictions</code>.
        </p>
      </header>

      <Form onSubmit={controller.save} sanitizeEmptyValues>
        <div className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-6">
          <JurisdictionFormBodyV2 />

          <footer className="flex items-center justify-end gap-2 pt-2 border-t border-[rgba(29,41,61,0.06)]">
            <Button variant="ghost" onClick={() => navigate("/jurisdictions")} type="button">
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={controller.saving}>
              {controller.saving ? "Creating…" : "Create jurisdiction"}
            </Button>
          </footer>
        </div>
      </Form>
    </div>
  );
}
