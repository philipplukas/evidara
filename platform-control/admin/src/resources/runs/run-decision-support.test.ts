/**
 * The guard AGENTS.md asks for: this fails if the TypeScript derivation returns.
 *
 * #908 moved the run decision support — the four operator questions, the
 * `not_applicable` stage projection, per-stage next actions, the overall summary —
 * into `platform-control`, so an agent, the CLI and alerting can reach the same
 * judgement the admin renders. The risk is not that someone reverts the move in one
 * commit; it is that a later change quietly re-adds "just this one" derivation here,
 * and the browser drifts back into being the place the real policy lives.
 *
 * AGENTS.md: *"the same rule enforced in two clients rather than once behind them —
 * the easier path becomes the real policy, and it is usually the weaker one."*
 *
 * This reads the source rather than the exports on purpose. A re-added helper that
 * is not exported is still a second implementation.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const read = (relative: string) => readFileSync(join(__dirname, relative), "utf8");

/** Names the derivation had before it moved server-side. */
const REMOVED_DERIVATION = [
  "buildPipelineDecisionSupport",
  "projectPipelineStages",
  "overallSummaryByStatus",
  "stageNextAction",
  "stageNeedsAction",
  "isTerminalFailureRunStatus",
];

describe("the decision-support derivation stays server-side", () => {
  it.each(REMOVED_DERIVATION)("run-decision-support.ts does not define %s", (name) => {
    expect(read("./run-decision-support.ts")).not.toContain(`function ${name}`);
  });

  it("run-decision-support.ts keeps only the DOM helpers a server cannot answer", () => {
    const source = read("./run-decision-support.ts");
    // These stay: an in-page anchor and a HashRouter-safe scroll are this page's
    // DOM, not a judgement about a run.
    expect(source).toContain("export function stageActionTarget");
    expect(source).toContain("export function scrollToInPageSection");
  });

  it("the banner reads the judgement from the payload instead of computing it", () => {
    const banner = read("./PipelineHealthBanner.tsx");
    expect(banner).toContain("health.decision_support");
    // The projection in particular: re-labelling stages here is what left every
    // other consumer of pipeline-health seeing a dead run's stages as `pending`.
    expect(banner).not.toContain("projectPipelineStages");
  });

  it("no other admin file re-implements the four questions", () => {
    // A cheap, honest scope: the run resource is where this lived and where it
    // would come back. Widening to the whole tree would make the test slow and
    // no more true.
    const banner = read("./PipelineHealthBanner.tsx");
    const detail = read("./RunDetailSectionsV2.tsx");
    for (const name of REMOVED_DERIVATION) {
      expect(banner).not.toContain(name);
      expect(detail).not.toContain(name);
    }
  });
});
