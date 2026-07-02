import { describe, expect, it } from "vitest";
import type { SourceRecord } from "../../lib/admin/dataProvider";
import type { LegalSearchHandoff } from "../../lib/admin/navigationContext";
import { buildSourceHandoffGuidance } from "./sourceHandoff";

const baseSource: SourceRecord = {
  id: "source-1",
  source_id: "source-1",
  name: "Federal collection",
  description: "Primary federal source",
  jurisdiction_id: "jur-1",
  authority_id: "auth-1",
  source_type: "official",
  document_family: "cases",
  status: "active",
  created_at: "2026-04-10T08:00:00Z",
  updated_at: "2026-04-10T09:00:00Z",
};

const handoff: LegalSearchHandoff = {
  hasOrigin: true,
  returnToUrl: "http://localhost:3101/?q=Art.%20754",
  query: "Art. 754 OR Verantwortlichkeit",
  scopeLabel: "Swiss federal law",
  selectedId: "decision-1",
};

describe("buildSourceHandoffGuidance", () => {
  it("frames the legal-search context for source operators", () => {
    const guidance = buildSourceHandoffGuidance(baseSource, handoff);

    expect(guidance?.whyYouAreHere).toContain("legal search");
    expect(guidance?.whyYouAreHere).toContain("Selected item: decision-1");
    expect(guidance?.whatToCheckNext).toContain("jurisdiction");
    expect(guidance?.whatToCheckNext).toContain("version history");
  });

  it("returns null when the visit did not originate from legal search", () => {
    const guidance = buildSourceHandoffGuidance(baseSource, {
      ...handoff,
      hasOrigin: false,
    });

    expect(guidance).toBeNull();
  });

  it("frames inactive and archived sources with their own attention cue", () => {
    const inactive = buildSourceHandoffGuidance({ ...baseSource, status: "inactive" }, handoff);
    expect(inactive?.whatToCheckNext).toContain("reactivated");

    const archived = buildSourceHandoffGuidance({ ...baseSource, status: "archived" }, handoff);
    expect(archived?.whatToCheckNext).toContain("read-only");
  });
});
