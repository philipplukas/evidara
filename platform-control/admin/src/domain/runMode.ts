/**
 * Run modes and how the panel names them (#743).
 *
 * The admin used to type this as `"preview" | "production"` and render it with
 * `mode === "production" ? "Production" : "Preview"`. Once the server gained
 * `acceptance`, every one of those sites silently labelled an acceptance run
 * **Preview** — falsifying the claim the mode exists to make, that an acceptance
 * run is recorded so it "can never be mistaken for production ingest".
 *
 * An acceptance run is the operator's rehearsal against a live portal: it is the
 * run that *produces* ADR-0030 evidence, so it reaches real infrastructure while
 * implying nothing about either key being turned. It is neither a preview (which
 * requires both keys) nor production. The panel has to say which one it is.
 *
 * Kept free of React so the labelling is unit-testable — the previous coverage
 * for this area lived in `admin/e2e/`, which no CI workflow executes.
 */

export type RunMode = "preview" | "production" | "acceptance";

export type RunModeDescriptor = {
  /** Badge text. */
  label: string;
  /** One sentence on what the run implies — the part the bare label loses. */
  detail: string;
};

const RUN_MODES: Record<RunMode, RunModeDescriptor> = {
  preview: {
    label: "Preview",
    detail: "A scoped rehearsal on an enabled template. Both ADR-0030 keys are turned.",
  },
  production: {
    label: "Production",
    detail: "Live ingest into the corpus.",
  },
  acceptance: {
    label: "Acceptance",
    detail:
      "An acceptance rehearsal against the live source, run to produce ADR-0030 evidence. " +
      "It is not production ingest and does not imply either key is turned.",
  },
};

/**
 * Describe a run mode, tolerating a value this build does not know.
 *
 * An unrecognised mode is echoed rather than mapped onto a familiar-looking
 * label: showing "Preview" for something we cannot identify is how the
 * acceptance mode got mislabelled in the first place.
 */
export function describeRunMode(mode: string | null | undefined): RunModeDescriptor {
  if (mode && mode in RUN_MODES) {
    return RUN_MODES[mode as RunMode];
  }
  return {
    label: mode ? `Unknown (${mode})` : "Unknown",
    detail: "This build does not recognise the run mode reported by the API.",
  };
}

export function runModeLabel(mode: string | null | undefined): string {
  return describeRunMode(mode).label;
}
