import { describe, expect, it } from "vitest";
import {
  classifyTemplate,
  describeCodeKey,
  describeConfigKey,
  describeProvenance,
  summarizeInventory,
} from "./blueprintLock";

const lock = (enabled: boolean, liveReady: boolean) => ({ enabled, live_ready: liveReady });

describe("classifyTemplate", () => {
  it("calls both keys open 'live'", () => {
    expect(classifyTemplate(lock(true, true)).id).toBe("live");
  });

  it("calls a shut config key on a live-ready provider operator-actionable", () => {
    // This is the group the whole screen exists for: 5 of 31 templates today
    // need nothing but the key an operator already owns.
    expect(classifyTemplate(lock(false, true)).id).toBe("operator-actionable");
  });

  it("lets the code key dominate — a shut provider is never operator-actionable", () => {
    // Both keys shut looks like "config key off" if you only read `enabled`,
    // and an operator who flips it would meet a refusal at run time anyway.
    expect(classifyTemplate(lock(false, false)).id).toBe("engineer-blocked");
    expect(classifyTemplate(lock(true, false)).id).toBe("engineer-blocked");
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
    ]);
    expect(summary).toEqual({
      live: 1,
      "operator-actionable": 2,
      "engineer-blocked": 2,
      total: 5,
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
