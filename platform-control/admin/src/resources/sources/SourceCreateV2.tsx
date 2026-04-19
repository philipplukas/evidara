/**
 * `SourceCreateV2` — v2 preview of the source-create flow. Uses
 * `useCreateController` + `<Form>` from `ra-core`; jurisdiction and
 * authority selects are the new Tailwind + radix `<Select>` primitive, so
 * the page has zero MUI imports.
 *
 * Authority choices are filtered live from the watched `jurisdiction_id`
 * via `filterAuthoritiesByJurisdiction` — same helper the MUI
 * `AuthoritySelectInput` uses — and validated with the matching
 * `isAuthorityValidForJurisdiction` predicate, so picking a mismatched
 * authority fails at submit with the same message the v1 flow ships.
 *
 * Deferred (intentional) on this page:
 *   - Acquisition-spec blueprint preview (overlay / provider template /
 *     server-side preview panel). Quiet footnote at the bottom of the page
 *     flags this; v1 remains canonical at `/sources/create` for the full
 *     wizard flow until parity lands in a later increment.
 */
"use client";

import { Form, required, useCreateController, useGetList, useNotify } from "ra-core";
import { useWatch } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import type {
  AuthorityRecord,
  JurisdictionRecord,
  SourceRecord,
} from "../../lib/admin/dataProvider";
import { Button, Select, type SelectChoice, TextInput } from "../../ui/primitives";
import {
  filterAuthoritiesByJurisdiction,
  formatReferenceLabel,
  isAuthorityValidForJurisdiction,
} from "../shared/referenceUtils";

const REFERENCE_LIST_PARAMS = {
  pagination: { page: 1, perPage: 250 },
  sort: { field: "name", order: "ASC" as const },
};

const CREATE_DEFAULTS = {
  document_family: null as string | null,
  description: null as string | null,
  jurisdiction_id: null as string | null,
  authority_id: null as string | null,
};

// Inner component: reads `jurisdiction_id` with `useWatch` so the
// authority `<Select>` re-renders with a filtered choice list whenever
// the operator changes jurisdiction. Splitting it out keeps the
// `useWatch` call inside the `<Form>`-provided react-hook-form context.
function AuthoritySelectField({ authorities }: { authorities: AuthorityRecord[] }) {
  const currentJurisdictionId = useWatch({ name: "jurisdiction_id" }) as string | null | undefined;

  const choices: SelectChoice[] = filterAuthoritiesByJurisdiction(
    authorities,
    currentJurisdictionId,
  ).map((authority) => ({
    id: authority.authority_id,
    name: formatReferenceLabel(authority),
  }));

  const validateAuthority = (value: unknown) => {
    if (value === null || value === undefined || value === "") {
      return undefined;
    }
    if (typeof value !== "string") {
      return "Select a valid authority.";
    }
    if (!isAuthorityValidForJurisdiction(authorities, value, currentJurisdictionId)) {
      return currentJurisdictionId
        ? "Select an authority within the chosen jurisdiction or a global authority."
        : "Select a global authority or choose a jurisdiction first.";
    }
    return undefined;
  };

  return (
    <Select
      // Force remount on jurisdiction change so the trigger re-reads its
      // value against the new choice set — same trick the v1 page uses
      // with `key={formData.jurisdiction_id}` on `AuthoritySelectInput`.
      key={currentJurisdictionId ?? "no-jurisdiction"}
      source="authority_id"
      label="Authority"
      choices={choices}
      required
      validate={[required(), validateAuthority]}
      helperText={
        currentJurisdictionId
          ? "Only authorities in the selected jurisdiction are shown."
          : "Select a jurisdiction first to load the matching authorities."
      }
      placeholder={currentJurisdictionId ? "Select an authority…" : "Select a jurisdiction first"}
    />
  );
}

export default function SourceCreateV2() {
  const notify = useNotify();
  const navigate = useNavigate();

  const jurisdictions = useGetList<JurisdictionRecord>("jurisdictions", REFERENCE_LIST_PARAMS);
  const authorities = useGetList<AuthorityRecord>("authorities", REFERENCE_LIST_PARAMS);

  const jurisdictionChoices: SelectChoice[] = (jurisdictions.data ?? []).map((jurisdiction) => ({
    id: jurisdiction.jurisdiction_id,
    name: formatReferenceLabel(jurisdiction),
  }));

  const controller = useCreateController<SourceRecord>({
    resource: "sources",
    mutationOptions: {
      onSuccess: () => {
        notify("Source created", { type: "success" });
        navigate("/sources");
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : String(error);
        notify(`Could not create source: ${message}`, { type: "error" });
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
          Create source <span className="text-[rgba(29,41,61,0.5)]">(v2 preview)</span>
        </h1>
        <p className="text-[14px] text-[rgba(29,41,61,0.7)] max-w-[72ch]">
          Jurisdiction + authority pickers use the new Tailwind{" "}
          <code className="font-mono text-[12px]">Select</code> primitive (radix-ui under the hood).
          Acquisition-spec blueprint preview is deferred — open{" "}
          <code className="font-mono text-[12px]">/sources/create</code> for the full MUI wizard. On
          success you'll be redirected to the MUI list at{" "}
          <code className="font-mono text-[12px]">/sources</code>.
        </p>
      </header>

      <Form onSubmit={controller.save} defaultValues={CREATE_DEFAULTS} sanitizeEmptyValues>
        <div className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85 p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-5">
          <TextInput
            source="name"
            label="Name"
            required
            validate={required()}
            helperText="Operator-facing display name."
            placeholder="e.g. Swiss Federal Court"
          />
          <TextInput
            source="description"
            label="Description"
            multiline
            helperText="Optional internal notes for operators reviewing this source."
          />
          <TextInput
            source="source_type"
            label="Source type"
            required
            validate={required()}
            helperText="`website` for Firecrawl crawls, `api` for structured endpoints."
            placeholder="website"
          />
          <TextInput
            source="document_family"
            label="Document family"
            helperText="Optional grouping label surfaced during operator review."
          />
          <Select
            source="jurisdiction_id"
            label="Jurisdiction"
            choices={jurisdictionChoices}
            required
            validate={required()}
            helperText="Choose the legal boundary this source belongs to."
            placeholder="Select a jurisdiction…"
          />
          <AuthoritySelectField authorities={authorities.data ?? []} />

          <footer className="flex items-center justify-end gap-2 pt-2 border-t border-[rgba(29,41,61,0.06)]">
            <Button variant="ghost" onClick={() => navigate("/sources")} type="button">
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={controller.saving}>
              {controller.saving ? "Creating…" : "Create source"}
            </Button>
          </footer>
        </div>
      </Form>

      {/*
       * UX-12.2 style: keep deferred-scope notice as a quiet footnote, not
       * a prominent card, so the v2 page still reads as intentional
       * coexistence rather than immaturity.
       */}
      <aside className="rounded-[10px] border border-dashed border-[rgba(29,41,61,0.1)] px-3 py-2.5 text-[11px] text-[rgba(29,41,61,0.55)] space-y-1">
        <p className="font-semibold text-[rgba(29,41,61,0.7)] text-[11px] uppercase tracking-[0.06em]">
          Deferred in this preview
        </p>
        <p>
          Acquisition-spec blueprint preview (country overlay + provider template + server-side
          preview panel) is intentionally absent. Use{" "}
          <code className="font-mono">/sources/create</code> for the complete MUI wizard until
          parity lands in a later increment.
        </p>
      </aside>
    </div>
  );
}
