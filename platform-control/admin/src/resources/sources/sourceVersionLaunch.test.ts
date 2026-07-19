import { describe, expect, it } from "vitest";
import type { RunReadiness } from "../../lib/admin/dataProvider";
import { deriveVersionLaunchGuards, describeLaunchBlockRollup } from "./sourceVersionLaunch";

/**
 * #667: the source detail page derived its launch buttons from version status
 * alone, so an approved version whose blueprint template was inert rendered
 * "Ready for preview or production runs", "No attention needed", and two enabled
 * buttons — then 400'd. `/v1/runs/readiness` knew the whole time.
 */

const readiness = (checks: RunReadiness["checks"]): RunReadiness => ({
  source_id: "src_1",
  source_version_id: "sv_1",
  mode: "production",
  ready: checks.every((check) => check.ok),
  checks,
});

/** The exact payload the issue captured for the ZH `canton_http_zh` source. */
const LOCKED = readiness([
  { code: "source_exists", ok: true, detail: "" },
  { code: "source_version_exists", ok: true, detail: "" },
  { code: "source_version_belongs_to_source", ok: true, detail: "" },
  { code: "mode_compatible_with_version_status", ok: true, detail: "" },
  { code: "acquisition_seed_present", ok: true, detail: "" },
  {
    code: "acquisition_lock_open",
    ok: false,
    detail: "Config key closed: template 'ch/canton_http_zh' is not enabled.",
  },
]);

describe("deriveVersionLaunchGuards", () => {
  it("disables BOTH launch buttons on an approved version behind a closed lock", () => {
    const guards = deriveVersionLaunchGuards({
      status: "approved",
      readiness: LOCKED,
      readinessError: null,
    });

    expect(guards.state).toBe("checked");
    expect(guards.preview.allowed).toBe(false);
    expect(guards.production.allowed).toBe(false);
    // And it explains the lock, not the generic "review the source/version pair".
    expect(guards.summary).toContain("not enabled for live acquisition");
  });

  it("allows both buttons on an approved version when readiness is green", () => {
    const guards = deriveVersionLaunchGuards({
      status: "approved",
      readiness: readiness([{ code: "acquisition_lock_open", ok: true, detail: "" }]),
      readinessError: null,
    });

    expect(guards.preview.allowed).toBe(true);
    expect(guards.production.allowed).toBe(true);
    expect(guards.summary).toBeNull();
  });

  it("treats the mode-dependent check as blocking production only, not preview", () => {
    const guards = deriveVersionLaunchGuards({
      status: "draft",
      readiness: readiness([
        { code: "mode_compatible_with_version_status", ok: false, detail: "" },
        { code: "acquisition_lock_open", ok: true, detail: "" },
      ]),
      readinessError: null,
    });

    expect(guards.preview.allowed).toBe(true);
    expect(guards.production.allowed).toBe(false);
  });

  it("refuses rather than promises while the probe is still in flight", () => {
    const guards = deriveVersionLaunchGuards({
      status: "approved",
      readiness: null,
      readinessError: null,
    });

    expect(guards.state).toBe("checking");
    expect(guards.preview.allowed).toBe(false);
    expect(guards.production.allowed).toBe(false);
  });

  it("does not convert a failed probe into a green light", () => {
    const guards = deriveVersionLaunchGuards({
      status: "approved",
      readiness: null,
      readinessError: "Network error",
    });

    expect(guards.state).toBe("unknown");
    // Not force-disabled — a transient blip must not lock the operator out —
    // but the uncertainty is stated on both buttons.
    expect(guards.preview.reason).toContain("could not be checked");
    expect(guards.production.reason).toContain("could not be checked");
  });
});

describe("describeLaunchBlockRollup", () => {
  it("replaces the 'ready for operator use' claim when a version is locked", () => {
    const rollup = describeLaunchBlockRollup([
      deriveVersionLaunchGuards({
        status: "approved",
        readiness: LOCKED,
        readinessError: null,
      }),
    ]);

    expect(rollup?.tone).toBe("warning");
    expect(rollup?.headline).toBe("1 version cannot launch a run right now.");
  });

  it("keeps the default lifecycle copy when everything really is launchable", () => {
    const rollup = describeLaunchBlockRollup([
      deriveVersionLaunchGuards({
        status: "approved",
        readiness: readiness([{ code: "acquisition_lock_open", ok: true, detail: "" }]),
        readinessError: null,
      }),
    ]);

    expect(rollup).toBeNull();
  });
});
