import { describe, expect, it } from "vitest";
import type { RunRecord } from "../../lib/admin/dataProvider";
import {
  describeRunState,
  getRunQueueKeyboardShortcutAction,
  isKeyboardShortcutInputTarget,
  selectAttentionRun,
  summarizeRunFilters,
} from "./RunList";

const completedRun: RunRecord = {
  id: "run_completed",
  run_id: "run_completed",
  source_id: "src_01",
  source_version_id: "sv_01",
  mode: "production",
  status: "completed",
  started_at: "2026-04-15T09:00:00Z",
  completed_at: "2026-04-15T09:30:00Z",
  artifacts_count: 4,
  captured_resources_count: 12,
  failure_reason: null,
  created_at: "2026-04-15T08:55:00Z",
  updated_at: "2026-04-15T09:30:00Z",
};

const pendingRun: RunRecord = {
  ...completedRun,
  id: "run_pending",
  run_id: "run_pending",
  status: "pending",
  started_at: null,
  completed_at: null,
};

const runningRun: RunRecord = {
  ...completedRun,
  id: "run_running",
  run_id: "run_running",
  status: "running",
  started_at: "2026-04-15T09:10:00Z",
  completed_at: null,
};

const failedRun: RunRecord = {
  ...completedRun,
  id: "run_failed",
  run_id: "run_failed",
  status: "failed",
  failure_reason: "Provider jobs were throttled.",
  started_at: "2026-04-15T09:05:00Z",
  completed_at: null,
};

describe("RunList helpers", () => {
  it("summarizes active filters for the operator inbox", () => {
    expect(summarizeRunFilters({})).toBe("");
    expect(summarizeRunFilters({ mode: "production", status: "pending" })).toBe(
      "mode: production · status: pending",
    );
  });

  it("prioritizes failed runs over running and pending work", () => {
    expect(selectAttentionRun([completedRun, pendingRun, runningRun, failedRun])).toBe(failedRun);
    expect(selectAttentionRun([completedRun, pendingRun, runningRun])).toBe(runningRun);
    expect(selectAttentionRun([completedRun, pendingRun])).toBe(pendingRun);
  });

  it("describes the queue state in operator language", () => {
    expect(describeRunState(failedRun)).toBe(
      "Blocked. Review the failure reason in the detail page.",
    );
    expect(describeRunState(completedRun)).toContain("Finished successfully");
  });

  it("ignores slash shortcuts inside text-entry targets", () => {
    expect(
      isKeyboardShortcutInputTarget({
        tagName: "input",
      } as unknown as EventTarget),
    ).toBe(true);
    expect(
      isKeyboardShortcutInputTarget({
        tagName: "div",
        isContentEditable: true,
      } as unknown as EventTarget),
    ).toBe(true);
    expect(isKeyboardShortcutInputTarget({ tagName: "button" } as unknown as EventTarget)).toBe(
      false,
    );
    expect(
      isKeyboardShortcutInputTarget({
        tagName: "select",
      } as unknown as EventTarget),
    ).toBe(true);
  });

  it("maps slash to attention focus and O to opening the attention run", () => {
    expect(
      getRunQueueKeyboardShortcutAction(
        {
          key: "/",
          altKey: false,
          ctrlKey: false,
          metaKey: false,
          defaultPrevented: false,
        } as Pick<KeyboardEvent, "altKey" | "ctrlKey" | "defaultPrevented" | "key" | "metaKey">,
        null,
        failedRun,
      ),
    ).toEqual({ type: "focus-attention" });

    expect(
      getRunQueueKeyboardShortcutAction(
        {
          key: "o",
          altKey: false,
          ctrlKey: false,
          metaKey: false,
          defaultPrevented: false,
        } as Pick<KeyboardEvent, "altKey" | "ctrlKey" | "defaultPrevented" | "key" | "metaKey">,
        null,
        failedRun,
      ),
    ).toEqual({ type: "open-attention", runId: "run_failed" });

    expect(
      getRunQueueKeyboardShortcutAction(
        {
          key: "o",
          altKey: false,
          ctrlKey: false,
          metaKey: false,
          defaultPrevented: false,
        } as Pick<KeyboardEvent, "altKey" | "ctrlKey" | "defaultPrevented" | "key" | "metaKey">,
        { tagName: "input" } as unknown as EventTarget,
        failedRun,
      ),
    ).toBeNull();
  });
});
