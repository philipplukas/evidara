import { describe, expect, it } from "vitest";
import type { CommentaryInsightRecord, CorrectionRecord } from "../../lib/admin/dataProvider";
import {
  buildCorrectionDiff,
  buildFieldEditEnvelope,
  draftFromInsight,
  formatDiffValue,
  PATCHABLE_INSIGHT_FIELDS,
  REVIEW_STATE_LABEL,
  reviewStateToLevel,
  sortCorrectionsNewestFirst,
  validateFieldEditDraft,
} from "./commentaryInsight";

const baseInsight: CommentaryInsightRecord = {
  id: "ins_01",
  insight_id: "ins_01",
  document_id: "doc_01",
  document_revision: 3,
  processing_manifest_id: "pm_01",
  insight_type: "referenced_provision",
  claim: "References Art. 754 OR.",
  display_text: "Art. 754 OR …",
  support: [{ document_id: "doc_01", ref_type: "passage" }],
  referenced_authorities: [],
  jurisdiction_id: "jur_ch_federal",
  jurisdiction_ids: ["jur_ch_federal"],
  authority_ids: ["auth_fedlex"],
  source_document_ids: ["doc_01"],
  last_correction_id: null,
  confidence: 0.78,
  review_state: "machine_verified",
  generator: { name: "extractor", version: "v1" },
  scores: {
    passage_present: 1,
    citation_parseable: 1,
    section_anchor_resolved: 1,
  },
};

describe("commentary insight helpers", () => {
  it("exposes the documented patchable fields", () => {
    expect([...PATCHABLE_INSIGHT_FIELDS]).toEqual(["claim", "display_text", "review_state"]);
  });

  it("labels every documented review state", () => {
    expect(REVIEW_STATE_LABEL.editor_approved).toBe("Editor-approved");
    expect(REVIEW_STATE_LABEL.machine_generated_unreviewed).toBe("Machine-generated (unreviewed)");
  });

  it("colours the review states in line with the operator UX", () => {
    expect(reviewStateToLevel("editor_approved")).toBe("healthy");
    expect(reviewStateToLevel("machine_verified")).toBe("info");
    expect(reviewStateToLevel("rejected")).toBe("degraded");
  });

  it("seeds the draft from the current insight values", () => {
    expect(draftFromInsight(baseInsight)).toEqual({
      claim: "References Art. 754 OR.",
      display_text: "Art. 754 OR …",
      review_state: "machine_verified",
      rationale: "",
    });
  });

  it("only includes changed fields in the field-edit envelope", () => {
    const envelope = buildFieldEditEnvelope(baseInsight, {
      claim: "Tightened claim",
      display_text: baseInsight.display_text,
      review_state: "editor_approved",
      rationale: "Tightened wording.",
    });
    expect(envelope.hasChanges).toBe(true);
    expect(envelope.payload).toEqual({
      claim: "Tightened claim",
      review_state: "editor_approved",
    });
    expect(envelope.original_snapshot).toEqual({
      claim: "References Art. 754 OR.",
      review_state: "machine_verified",
    });
  });

  it("flags a no-op draft as having no changes", () => {
    const envelope = buildFieldEditEnvelope(baseInsight, draftFromInsight(baseInsight));
    expect(envelope.hasChanges).toBe(false);
    expect(envelope.payload).toEqual({});
  });

  it("requires a rationale and rejects empty fields", () => {
    const result = validateFieldEditDraft({
      claim: "",
      display_text: "  ",
      review_state: "machine_verified",
      rationale: "",
    });
    expect(result.ok).toBe(false);
    expect(result.errors.claim).toMatch(/empty/i);
    expect(result.errors.display_text).toMatch(/empty/i);
    expect(result.errors.rationale).toMatch(/required/i);
  });

  it("rejects rationales longer than 2000 characters", () => {
    const result = validateFieldEditDraft({
      claim: "ok",
      display_text: "ok",
      review_state: "machine_verified",
      rationale: "x".repeat(2001),
    });
    expect(result.ok).toBe(false);
    expect(result.errors.rationale).toMatch(/2000/);
  });

  it("accepts a valid draft", () => {
    const result = validateFieldEditDraft({
      claim: "ok",
      display_text: "ok",
      review_state: "editor_approved",
      rationale: "Valid rationale.",
    });
    expect(result).toEqual({ ok: true, errors: {} });
  });

  it("builds an alphabetised diff for a correction envelope", () => {
    const correction: CorrectionRecord = {
      id: "cor_01",
      correction_id: "cor_01",
      target_entity_type: "commentary_insight",
      target_entity_id: "ins_01",
      correction_type: "field_edit",
      payload: { claim: "after", review_state: "editor_approved" },
      original_snapshot: { claim: "before", review_state: "machine_verified" },
      operator_id: "op_x",
      pipeline_run_id: null,
      rationale: "Edit",
      status: "applied",
      created_at: "2026-04-25T09:00:00Z",
      applied_at: "2026-04-25T09:00:00Z",
    };
    expect(buildCorrectionDiff(correction)).toEqual([
      { field: "claim", before: "before", after: "after" },
      { field: "review_state", before: "machine_verified", after: "editor_approved" },
    ]);
  });

  it("formats null and undefined diff values without collapsing them", () => {
    expect(formatDiffValue(null)).toBe("null");
    expect(formatDiffValue(undefined)).toBe("—");
    expect(formatDiffValue("text")).toBe("text");
    expect(formatDiffValue(42)).toBe("42");
    expect(formatDiffValue({ a: 1 })).toContain('"a": 1');
  });

  it("sorts corrections newest-first", () => {
    const old: CorrectionRecord = {
      id: "cor_old",
      correction_id: "cor_old",
      target_entity_type: "commentary_insight",
      target_entity_id: "ins_01",
      correction_type: "field_edit",
      payload: {},
      original_snapshot: {},
      operator_id: "op",
      pipeline_run_id: null,
      rationale: "old",
      status: "applied",
      created_at: "2026-04-20T09:00:00Z",
      applied_at: "2026-04-20T09:00:00Z",
    };
    const fresh: CorrectionRecord = { ...old, id: "cor_new", created_at: "2026-04-25T09:00:00Z" };
    expect(sortCorrectionsNewestFirst([old, fresh])[0]?.id).toBe("cor_new");
    expect(sortCorrectionsNewestFirst([old, fresh])[1]?.id).toBe("cor_old");
  });
});
