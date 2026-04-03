import { describe, expect, it } from "vitest";
import type { AuthorityRecord } from "../../lib/admin/dataProvider";
import {
  filterAuthoritiesByJurisdiction,
  formatReferenceLabel,
  isAuthorityValidForJurisdiction,
} from "./referenceUtils";

const authorities: AuthorityRecord[] = [
  {
    id: "auth_01",
    authority_id: "auth_01",
    jurisdiction_id: "jur_01",
    name: "Federal Court",
    slug: "federal-court",
    created_at: "2026-04-03T09:00:00Z",
    updated_at: "2026-04-03T09:00:00Z",
  },
  {
    id: "auth_02",
    authority_id: "auth_02",
    jurisdiction_id: "jur_02",
    name: "Cantonal Court",
    slug: "cantonal-court",
    created_at: "2026-04-03T09:00:00Z",
    updated_at: "2026-04-03T09:00:00Z",
  },
  {
    id: "auth_global",
    authority_id: "auth_global",
    jurisdiction_id: null,
    name: "Global Bulletin",
    slug: "global-bulletin",
    created_at: "2026-04-03T09:00:00Z",
    updated_at: "2026-04-03T09:00:00Z",
  },
];

describe("referenceUtils", () => {
  it("formats reference labels with names and slugs", () => {
    expect(
      formatReferenceLabel({
        name: "Federal Court",
        slug: "federal-court",
      }),
    ).toBe("Federal Court (federal-court)");
  });

  it("filters authorities to the selected jurisdiction", () => {
    expect(filterAuthoritiesByJurisdiction(authorities, "jur_01")).toEqual([
      authorities[0],
      authorities[2],
    ]);
    expect(filterAuthoritiesByJurisdiction(authorities, null)).toEqual([authorities[2]]);
  });

  it("validates authority choices against the selected jurisdiction", () => {
    expect(isAuthorityValidForJurisdiction(authorities, "auth_01", "jur_01")).toBe(true);
    expect(isAuthorityValidForJurisdiction(authorities, "auth_01", "jur_02")).toBe(false);
    expect(isAuthorityValidForJurisdiction(authorities, "auth_global", "jur_02")).toBe(true);
    expect(isAuthorityValidForJurisdiction(authorities, "auth_global", null)).toBe(true);
    expect(isAuthorityValidForJurisdiction(authorities, "auth_01", null)).toBe(false);
  });
});
