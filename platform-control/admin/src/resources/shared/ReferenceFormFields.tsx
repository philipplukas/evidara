/**
 * Tailwind + ra-core reference-data form fields (ADR-0026).
 *
 * Ported from the retired MUI `ReferenceInputs.tsx`:
 *   - `JurisdictionSelectField` — data-fetched parent picker built on the
 *     `<Select>` primitive (replaces the MUI `JurisdictionSelectInput`).
 *   - `AuthorityScopeChangeAlert` / `ReferenceSlugChangeAlert` — `useWatch`
 *     driven warnings, rendered with the `<InlineAlert>` primitive.
 *
 * The pure helpers (slug validator, select-state describers) live here too so
 * the create/edit form bodies and their unit tests share one module.
 */
"use client";

import { useGetList, type Validator } from "ra-core";
import { useWatch } from "react-hook-form";
import type { JurisdictionRecord } from "../../lib/admin/dataProvider";
import { InlineAlert, Select, type SelectChoice } from "../../ui/primitives";
import { formatReferenceLabel } from "./referenceUtils";

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 250 },
  sort: { field: "name", order: "ASC" as const },
};

export type ReferenceSelectState = {
  severity: "info" | "warning" | "error";
  title: string;
  message: string;
};

export const REFERENCE_SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const referenceSlugHelperText =
  "Use lowercase letters, numbers, and hyphens only. Keep the slug stable once records reference it.";

export const referenceSlugValidator: Validator = (value: unknown) => {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }

  if (typeof value !== "string" || !REFERENCE_SLUG_PATTERN.test(value)) {
    return "Use lowercase letters, numbers, and hyphens only.";
  }

  return undefined;
};

export function describeJurisdictionSelectState({
  isPending,
  hasError,
  choiceCount,
}: {
  isPending: boolean;
  hasError: boolean;
  choiceCount: number;
}): ReferenceSelectState | null {
  if (hasError) {
    return {
      severity: "error",
      title: "Unable to load jurisdictions",
      message: "Try again after the reference-data service recovers.",
    };
  }

  if (isPending && choiceCount === 0) {
    return {
      severity: "info",
      title: "Loading jurisdictions",
      message: "The selector will unlock once the jurisdiction list arrives.",
    };
  }

  if (!isPending && choiceCount === 0) {
    return {
      severity: "warning",
      title: "No jurisdictions available",
      message: "Seed at least one jurisdiction before creating or editing authorities.",
    };
  }

  return null;
}

export function describeAuthoritySelectState({
  isPending,
  hasError,
  choiceCount,
  jurisdictionId,
}: {
  isPending: boolean;
  hasError: boolean;
  choiceCount: number;
  jurisdictionId?: string | null;
}): ReferenceSelectState | null {
  if (hasError) {
    return {
      severity: "error",
      title: "Unable to load authorities",
      message: "Try again after the reference-data service recovers.",
    };
  }

  if (isPending && choiceCount === 0) {
    return {
      severity: "info",
      title: "Loading authorities",
      message: "The selector will unlock once the authority list arrives.",
    };
  }

  if (!isPending && choiceCount === 0) {
    return {
      severity: "warning",
      title: jurisdictionId ? "No matching authorities" : "No global authorities available",
      message: jurisdictionId
        ? "Create a scoped authority for this jurisdiction, or switch to a jurisdiction that already has one."
        : "Seed a global authority before continuing.",
    };
  }

  return null;
}

function ReferenceStateAlert({ state }: { state: ReferenceSelectState }) {
  return (
    <InlineAlert tone={state.severity}>
      <p className="font-semibold text-[var(--foreground)]">{state.title}</p>
      <p>{state.message}</p>
    </InlineAlert>
  );
}

/**
 * Parent-jurisdiction picker for authorities. Fetches jurisdictions live and
 * feeds them into the `<Select>` primitive; `allowEmpty` maps the empty choice
 * back to `null` so an authority can stay global.
 */
export function JurisdictionSelectField() {
  const jurisdictions = useGetList<JurisdictionRecord>("jurisdictions", LIST_PARAMS);
  const choices: SelectChoice[] = (jurisdictions.data ?? []).map((jurisdiction) => ({
    id: jurisdiction.jurisdiction_id,
    name: formatReferenceLabel(jurisdiction),
  }));

  if (jurisdictions.error) {
    return (
      <ReferenceStateAlert
        state={{
          severity: "error",
          title: "Unable to load jurisdictions",
          message: "Try again after the reference-data service recovers.",
        }}
      />
    );
  }

  const state = describeJurisdictionSelectState({
    isPending: jurisdictions.isPending,
    hasError: false,
    choiceCount: choices.length,
  });

  return (
    <div className="space-y-2">
      {state ? <ReferenceStateAlert state={state} /> : null}
      <Select
        source="jurisdiction_id"
        label="Jurisdiction"
        choices={choices}
        allowEmpty
        emptyLabel="No jurisdiction (global)"
        disabled={jurisdictions.isPending && choices.length === 0}
        helperText="Global authorities are shared everywhere. Scoped authorities only appear within the selected jurisdiction."
        placeholder="Select a jurisdiction…"
      />
    </div>
  );
}

/**
 * Warns when the edited slug diverges from the persisted one — a slug change
 * can break seeded data, links, and operator notes pointing at the old id.
 */
export function ReferenceSlugChangeAlert({
  originalSlug,
  entityLabel,
}: {
  originalSlug?: string | null;
  entityLabel: string;
}) {
  const currentSlug = useWatch({ name: "slug" }) as string | undefined;

  if (!originalSlug || !currentSlug || originalSlug === currentSlug) {
    return null;
  }

  return (
    <InlineAlert tone="warning">
      <p className="font-semibold text-[var(--foreground)]">{entityLabel} slug changed</p>
      <p>
        Changing the slug from <strong>{originalSlug}</strong> to <strong>{currentSlug}</strong> can
        break seeded data, links, and operator notes that point at the old identifier.
      </p>
    </InlineAlert>
  );
}

/**
 * Explains the scope implication of the watched `jurisdiction_id`. On create
 * (`originalJurisdictionId === undefined`) it describes global-vs-scoped; on
 * edit it warns when the scope actually changed.
 */
export function AuthorityScopeChangeAlert({
  originalJurisdictionId,
}: {
  originalJurisdictionId?: string | null;
}) {
  const currentJurisdictionId = useWatch({ name: "jurisdiction_id" }) as string | null | undefined;

  if (originalJurisdictionId === undefined) {
    if (!currentJurisdictionId) {
      return (
        <InlineAlert tone="warning">
          <p className="font-semibold text-[var(--foreground)]">Global authority</p>
          <p>
            Leaving jurisdiction blank makes this authority a global fallback that can be reused
            across every jurisdiction.
          </p>
        </InlineAlert>
      );
    }

    return (
      <InlineAlert tone="info">
        <p className="font-semibold text-[var(--foreground)]">Scoped authority</p>
        <p>
          This authority will be scoped to the selected jurisdiction and will still show alongside
          global authorities where operators can pick either scope.
        </p>
      </InlineAlert>
    );
  }

  if (currentJurisdictionId === originalJurisdictionId) {
    return null;
  }

  if (!currentJurisdictionId) {
    return (
      <InlineAlert tone="warning">
        <p className="font-semibold text-[var(--foreground)]">Global authority</p>
        <p>
          Leaving jurisdiction blank makes this authority a global fallback that can be reused
          across every jurisdiction.
        </p>
      </InlineAlert>
    );
  }

  return (
    <InlineAlert tone="warning">
      <p className="font-semibold text-[var(--foreground)]">Authority scope changed</p>
      <p>
        Moving this authority into a jurisdiction changes where it appears in operator forms and may
        require downstream records to be reviewed.
      </p>
    </InlineAlert>
  );
}
