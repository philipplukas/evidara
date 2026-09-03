/**
 * Run fixtures for tests, built from the contract-derived record types.
 *
 * Every run test used to hand-write a full literal. When #737 derived
 * `RunRecord`/`RunListRecord` from the contract — picking up `scope`, `replay`
 * and `refused`, which the hand-written `RunBase` never had — that meant the
 * same three fields pasted into five files, and the next field the API adds
 * would mean five more edits.
 *
 * These builders take the defaults from one place and let each test override
 * only the fields it is actually about, so a test reads as its own premise
 * rather than as a wall of boilerplate.
 */

import type { RunListRecord, RunRecord } from "../dataProvider";

/**
 * A completed preview run. Deliberately the boring case: tests override
 * `status`/`mode` to describe the case they care about.
 */
export const buildRunRecord = (overrides: Partial<RunRecord> = {}): RunRecord => ({
  id: "run-preview",
  run_id: "run-preview",
  source_id: "source-1",
  source_version_id: "version-1",
  mode: "preview",
  scope: { kind: "full_source" },
  replay: null,
  replay_checkpoint: null,
  status: "completed",
  started_at: "2026-04-15T09:00:00Z",
  completed_at: "2026-04-15T09:30:00Z",
  artifacts_count: 4,
  captured_resources_count: 12,
  failure_reason: null,
  refused: false,
  // Captured and published are separate numbers as of #853: a FAILED dispatch
  // keeps its artifacts but publishes none of them. The boring case published
  // everything it captured.
  published_artifacts_count: 4,
  publication_withheld: false,
  created_at: "2026-04-15T08:55:00Z",
  updated_at: "2026-04-15T09:30:00Z",
  ...overrides,
});

/**
 * One row of the run queue. Carries `source_name`/`version_label`, which the
 * detail response does not — see `RunListItem` in `dataProvider.ts`.
 */
export const buildRunListRecord = (overrides: Partial<RunListRecord> = {}): RunListRecord => ({
  id: "run-preview",
  run_id: "run-preview",
  source_id: "source-1",
  source_version_id: "version-1",
  mode: "preview",
  status: "completed",
  started_at: "2026-04-15T09:00:00Z",
  completed_at: "2026-04-15T09:30:00Z",
  artifacts_count: 4,
  captured_resources_count: 12,
  failure_reason: null,
  refused: false,
  // Captured and published are separate numbers as of #853: a FAILED dispatch
  // keeps its artifacts but publishes none of them. The boring case published
  // everything it captured.
  published_artifacts_count: 4,
  publication_withheld: false,
  created_at: "2026-04-15T08:55:00Z",
  updated_at: "2026-04-15T09:30:00Z",
  source_name: "Zurich decisions",
  version_label: "v1",
  ...overrides,
});
