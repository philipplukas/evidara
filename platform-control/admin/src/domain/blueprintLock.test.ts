import { describe, expect, it } from "vitest";
import {
  classifyTemplate,
  describeCodeKey,
  describeConfigKey,
  describeProvenance,
  summarizeInventory,
} from "./blueprintLock";

const lock = (enabled: boolean, liveReady: boolean) => ({ enabled, live_ready: liveReady });

/** A template whose provider is built but has no acceptance evidence yet (#743). */
const awaitingEvidence = (enabled: boolean) => ({
  enabled,
  live_ready: false,
  acquisition_readiness: "awaiting_evidence" as const,
});

describe("classifyTemplate", () => {
  it("calls both keys open 'live'", () => {
    expect(classifyTemplate(lock(true, true)).id).toBe("live");
  });

  it("calls a shut config key on a live-ready provider operator-actionable", () => {
    // This is the group the whole screen exists for: 5 of 31 templates today
    // need nothing but the key an operator already owns.
    expect(classifyTemplate(lock(false, true)).id).toBe("operator-actionable");
  });

  it("lets a scaffold code key dominate — it is never operator-actionable", () => {
    // Both keys shut looks like "config key off" if you only read `enabled`,
    // and an operator who flips it would meet a refusal at run time anyway.
    expect(classifyTemplate(lock(false, false)).id).toBe("engineer-blocked");
    expect(classifyTemplate(lock(true, false)).id).toBe("engineer-blocked");
  });

  it("does not send an operator to an engineer for a provider that is merely unproven", () => {
    // The #743 defect: `live_ready: false` used to mean "scaffold" unconditionally,
    // so a built-and-verified provider was reported as needing engineering. It needs
    // an acceptance run, which the operator dispatches themselves.
    expect(classifyTemplate(awaitingEvidence(false)).id).toBe("awaiting-acceptance");
    expect(classifyTemplate(awaitingEvidence(true)).id).toBe("awaiting-acceptance");
  });

  it("never infers awaiting_evidence from the legacy boolean alone", () => {
    // Only the server can assert that state; guessing it client-side would invent
    // an operator action for a provider that genuinely has no implementation.
    expect(classifyTemplate(lock(false, false)).id).toBe("engineer-blocked");
  });
});

describe("summarizeInventory", () => {
  it("counts each lock class and the total", () => {
    const summary = summarizeInventory([
      lock(true, true),
      lock(false, true),
      lock(false, true),
      lock(false, false),
      lock(true, false),
      awaitingEvidence(false),
    ]);
    expect(summary).toEqual({
      live: 1,
      "operator-actionable": 2,
      "awaiting-acceptance": 1,
      "engineer-blocked": 2,
      total: 6,
    });
  });
});

describe("key descriptors", () => {
  it("tells the operator a shut config key is theirs to turn", () => {
    const config = describeConfigKey(lock(false, true));
    expect(config.state).toBe("shut");
    expect(config.ownerHint).toContain("yours");
  });

  it("tells the operator a shut code key needs an engineer", () => {
    const code = describeCodeKey(lock(false, false));
    expect(code.state).toBe("shut");
    expect(code.ownerHint).toContain("engineer");
  });

  it("does not describe an open code key as operator-owned", () => {
    expect(describeCodeKey(lock(false, true)).ownerHint).not.toContain("yours");
  });
});

describe("describeProvenance", () => {
  it("distinguishes an untouched shipped default from an operator override", () => {
    expect(
      describeProvenance({ source: "default", default_enabled: false, updated_by: null }),
    ).toContain("never overridden");
    expect(
      describeProvenance({ source: "override", default_enabled: false, updated_by: "op_123" }),
    ).toContain("op_123");
  });

  it("attributes to the operator key, never to a person", () => {
    // Attribution is key-shaped: every human sharing an operator API key
    // resolves to the same identity, so the copy must not imply otherwise.
    expect(
      describeProvenance({ source: "override", default_enabled: false, updated_by: "op_123" }),
    ).toContain("operator key");
  });
});
