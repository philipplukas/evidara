/*
 * SPIKE — shared form body for AuthorityCreateV2 + AuthorityEditV2.
 *
 * Encapsulates the validators and field set so create and edit render
 * identical UI and diverge only in the wiring (save function, defaults).
 *
 * Intentionally deferred from the spike:
 *   - `JurisdictionSelectInput` — requires porting a `<Select>` primitive,
 *     which is the biggest remaining form piece and gets the next
 *     increment. Jurisdiction is sent as `null` on create, preserved
 *     as-is on edit.
 *   - `AuthorityScopeChangeAlert`, `ReferenceSlugChangeAlert` — pure
 *     presentational alerts that use `useWatch`; adding them is a
 *     10-line follow-up once the form path is accepted.
 */
"use client";

import { required } from "ra-core";
import { TextInput } from "../../ui/primitives";
import { referenceSlugValidator } from "../shared/ReferenceInputs";

export function AuthorityFormBodyV2({ idDisabled = false }: { idDisabled?: boolean }) {
  return (
    <div className="space-y-5">
      {idDisabled ? (
        <TextInput
          source="authority_id"
          label="Authority ID"
          disabled
          helperText="Immutable identifier used by linked records."
        />
      ) : null}
      <TextInput
        source="name"
        label="Name"
        required
        validate={required()}
        helperText="Display name shown in reference lists and operator forms."
        placeholder="e.g. Bundesgericht"
      />
      <TextInput
        source="slug"
        label="Slug"
        required
        validate={[required(), referenceSlugValidator]}
        helperText="Use lowercase letters, numbers, and hyphens only. Keep the slug stable once records reference it."
        placeholder="e.g. bger"
      />
    </div>
  );
}
