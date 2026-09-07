/**
 * `run-decision-support` — what is left of it: the DOM concerns.
 *
 * The JUDGEMENT that used to live here — the four operator questions, the
 * `not_applicable` stage projection, per-stage next actions, the overall summary
 * sentence — now comes from `platform-control` on the pipeline-health payload
 * (`decision_support`), because the browser was the only consumer that could
 * reach it. An agent, the CLI and alerting all had to either go without or
 * re-derive it, which is AGENTS.md's "same rule enforced in two clients ... the
 * easier path becomes the real policy, and it is usually the weaker one" (#908).
 *
 * What stays is the part a server cannot answer: which in-page anchor a stage's
 * action button should scroll to, and how to scroll there without the HashRouter
 * treating it as a route change.
 *
 * `run-decision-support.guard.test.ts` fails if the derivation comes back.
 */
import type { components } from "../../lib/api/generated/platform-control";

type PipelineStage = components["schemas"]["RunPipelineHealthStage"];

export function stageActionTarget(
  stage: Pick<PipelineStage, "stage">,
  options: { legalSearchUrl?: string; evidenceRunbookPath: string },
): { label: string; href: string } {
  if (stage.stage === "acquisition") {
    return { label: "Jump to provider jobs", href: "#provider-jobs-section" };
  }
  if (stage.stage === "document_intelligence") {
    return { label: "Jump to DI processing", href: "#di-processing-status-section" };
  }
  if (stage.stage === "projection") {
    return { label: "Jump to document lifecycle", href: "#document-lifecycle-section" };
  }
  if (options.legalSearchUrl) {
    return { label: "Open legal-search verification", href: options.legalSearchUrl };
  }
  return { label: "Open evidence runbook", href: options.evidenceRunbookPath };
}

/**
 * `sectionIdFromAnchor` — strip the leading `#` from an in-page anchor href so
 * it can be resolved with `document.getElementById`. Callers pass the raw
 * `stageActionTarget` href (e.g. `#di-processing-status-section`).
 */
export function sectionIdFromAnchor(href: string): string {
  return href.startsWith("#") ? href.slice(1) : href;
}

/**
 * `scrollToInPageSection` — smooth-scroll to the element behind an in-page
 * anchor **without** letting the click reach react-admin's HashRouter.
 *
 * These detail pages render under a `HashRouter`, so a plain `<a href="#foo">`
 * click mutates `location.hash` to `#foo`, which the router parses as a route
 * change and bounces the operator to the "Not Found" page (issue: jump links
 * left the run detail entirely). Resolving the target element and calling
 * `scrollIntoView` ourselves keeps navigation entirely client-side and never
 * touches the hash. No-ops safely if the element is not in the DOM.
 */
export function scrollToInPageSection(href: string): void {
  if (typeof document === "undefined") {
    return;
  }
  const target = document.getElementById(sectionIdFromAnchor(href));
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
}
