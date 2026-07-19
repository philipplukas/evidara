import { describe, expect, it } from "vitest";
import { CAPABILITIES, NOT_YET } from "./content";

/**
 * The copy-integrity gate.
 *
 * This page makes claims about what a legal-technology system can do. The
 * cost of an overclaim here is not a bounced lead — it is a professional
 * relying on a capability that does not exist. These tests make the
 * "no claim without evidence" rule mechanical instead of cultural.
 */
describe("marketing claims", () => {
  const all = [...CAPABILITIES, ...NOT_YET];

  it("uses unique claim ids so PR sign-off can reference them unambiguously", () => {
    const ids = all.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it.each(all.map((c) => [c.id, c] as const))("%s cites evidence for its claim", (_id, claim) => {
    expect(claim.evidence.trim().length).toBeGreaterThan(20);
    // Evidence must point at something concrete — a source path, a contract,
    // or a numbered ADR — not a vibe.
    expect(claim.evidence).toMatch(/\.(ts|tsx|py|yaml|json)|ADR-\d{4}/);
  });

  it.each(
    CAPABILITIES.map((c) => [c.id, c] as const),
  )("%s (a present-tense capability) does not hedge into the future", (_id, claim) => {
    // "will", "soon", "planned", "roadmap" belong in NOT_YET, not here. A
    // capability card that hedges is an aspiration wearing a fact's clothes.
    expect(`${claim.title} ${claim.body}`).not.toMatch(
      /\b(will soon|coming soon|planned|on the roadmap|in future|shortly)\b/i,
    );
  });

  it("keeps the two lists disjoint", () => {
    const capabilityIds = new Set(CAPABILITIES.map((c) => c.id));
    for (const limitation of NOT_YET) {
      expect(capabilityIds.has(limitation.id)).toBe(false);
    }
  });

  it("never claims an AI agent answers legal questions (ADR-0033 §4)", () => {
    const prose = CAPABILITIES.map((c) => `${c.title} ${c.body}`).join(" ");
    expect(prose).not.toMatch(/\b(ask (it|our)|answers your|AI (assistant|agent|lawyer)|chat)\b/i);
  });

  it("never claims semantic or vector search — retrieval is BM25 today", () => {
    const prose = CAPABILITIES.map((c) => `${c.title} ${c.body}`).join(" ");
    expect(prose).not.toMatch(/\b(semantic search|vector search|embeddings?|RAG)\b/i);
  });

  it("keeps the limitations list substantive", () => {
    // If someone trims this to a token disclaimer, the gate fails.
    for (const claim of NOT_YET) {
      expect(claim.body.length).toBeGreaterThan(60);
    }
  });
});
