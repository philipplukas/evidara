/**
 * Compile-time pins for the wire types that are still hand-written.
 *
 * #695 derived most of the admin's wire types from the generated contract. Three
 * could not be aliased in the same change without cascading past the data
 * provider — `RunBase` (and the `RunListItem` built on it) and `SourceVersion`.
 * Until #737 aliases them, this file asserts that every field they *do* declare
 * still matches the contract's type for that field.
 *
 * What this catches: a renamed field (the `Pick` stops resolving) and a retyped
 * field (the mutual-assignability check fails).
 *
 * What this does NOT catch: a field **added** to the contract. That is the known
 * gap, and it is exactly why #737 exists rather than this file being the
 * endpoint. `Schemas["RunResponse"]` already carries `scope`, `replay`,
 * `replay_checkpoint` and `refused` that `RunBase` does not.
 *
 * There is no runtime export here on purpose — the assertions are types, and
 * `npm run typecheck` is where they fire.
 */

import type { RunBase, RunListItem, SourceVersion } from "../admin/dataProvider";
import type { Schemas } from "./schemas";

/** Mutual assignability — invariant, so a widened *or* narrowed field fails. */
type Exact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;

/** Fails to compile unless `T` is exactly `true`. */
type AssertExact<T extends true> = T;

/**
 * The subset of the contract schema covering the fields the hand-written type
 * declares. If the server renames one, `Pick` no longer resolves and this line
 * is the error.
 */
type ContractSubset<Schema, Hand extends Record<string, unknown>> = Pick<
  Schema,
  Extract<keyof Hand, keyof Schema>
>;

type RunBaseFieldsMatchContract = AssertExact<
  Exact<RunBase, ContractSubset<Schemas["RunResponse"], RunBase>>
>;

type RunListItemFieldsMatchContract = AssertExact<
  Exact<RunListItem, ContractSubset<Schemas["RunListItemResponse"], RunListItem>>
>;

/**
 * `acquisition_spec` is deliberately excluded: the contract's generated union
 * types `seed_url` as `string | null | undefined` where the admin's
 * `AcquisitionSpec` requires it present, and reconciling that is #737's job
 * because it reaches into `sourceVersionForm.ts`'s form state.
 */
type SourceVersionScalarFields = Omit<SourceVersion, "acquisition_spec">;

type SourceVersionFieldsMatchContract = AssertExact<
  Exact<
    SourceVersionScalarFields,
    ContractSubset<Schemas["SourceVersionResponse"], SourceVersionScalarFields>
  >
>;

export type {
  RunBaseFieldsMatchContract,
  RunListItemFieldsMatchContract,
  SourceVersionFieldsMatchContract,
};
