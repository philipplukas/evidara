/**
 * Shared form body for JurisdictionCreateV2 + JurisdictionEditV2.
 *
 * Mirrors `AuthorityFormV2.tsx`: same primitives, same validators, same
 * field ergonomics. The only difference from the authority form is the
 * field set (jurisdictions have `name` + `slug` only — no jurisdiction /
 * scope selection of their own).
 */
"use client";

import { required } from "ra-core";
import { TextInput } from "../../ui/primitives";
import { referenceSlugValidator } from "../shared/ReferenceInputs";

export function JurisdictionFormBodyV2({ idDisabled = false }: { idDisabled?: boolean }) {
  return (
    <div className="space-y-5">
      {idDisabled ? (
        <TextInput
          source="jurisdiction_id"
          label="Jurisdiction ID"
          disabled
          helperText="Immutable identifier used by linked records."
        />
      ) : null}
      <TextInput
        source="name"
        label="Name"
        required
        validate={required()}
        helperText="Display name shown in lists and source forms."
        placeholder="e.g. Switzerland"
      />
      <TextInput
        source="slug"
        label="Slug"
        required
        validate={[required(), referenceSlugValidator]}
        helperText="Use lowercase letters, numbers, and hyphens only. Keep the slug stable once records reference it."
        placeholder="e.g. ch"
      />
    </div>
  );
}
