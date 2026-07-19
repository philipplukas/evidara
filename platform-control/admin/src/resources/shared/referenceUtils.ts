"use client";

import type { AuthorityRecord } from "../../lib/admin/dataProvider";

/**
 * `getList` params for the reference pickers (jurisdiction / authority).
 *
 * `/v1/reference-data/{jurisdictions,authorities}` return the whole table with
 * no `limit`, and the data provider windows the array client-side, so this
 * `perPage` is purely "how much of what we already hold may the picker see".
 * It used to be 250 against 2,169 jurisdictions, which is how Zürich and every
 * country-level jurisdiction became unreachable from the source and authority
 * wizards (#666).
 *
 * The number is a safety rail, not a correctness guarantee: pickers built on
 * `<Combobox>` are passed the `total` from the same query and say so out loud if
 * the fetch ever comes back short, so growth past this bound degrades to a
 * visible warning rather than a silent truncation.
 */
export const REFERENCE_PICKER_LIST_PARAMS = {
  pagination: { page: 1, perPage: 25_000 },
  sort: { field: "name", order: "ASC" as const },
};

type ReferenceLabelRecord = {
  name: string;
  slug: string;
};

export const formatReferenceLabel = (record: ReferenceLabelRecord | null | undefined): string =>
  record ? `${record.name} (${record.slug})` : "—";

export const filterAuthoritiesByJurisdiction = (
  authorities: AuthorityRecord[],
  jurisdictionId?: string | null,
): AuthorityRecord[] =>
  authorities.filter((authority) =>
    jurisdictionId
      ? authority.jurisdiction_id === jurisdictionId || authority.jurisdiction_id === null
      : authority.jurisdiction_id === null,
  );

export const isAuthorityValidForJurisdiction = (
  authorities: AuthorityRecord[],
  authorityId: string | null | undefined,
  jurisdictionId?: string | null,
): boolean => {
  if (!authorityId) {
    return true;
  }

  return authorities.some(
    (authority) =>
      authority.authority_id === authorityId &&
      (jurisdictionId
        ? authority.jurisdiction_id === jurisdictionId || authority.jurisdiction_id === null
        : authority.jurisdiction_id === null),
  );
};
