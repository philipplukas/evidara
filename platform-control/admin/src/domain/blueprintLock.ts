/**
 * Pure classification helpers for the blueprint coverage inventory (#668).
 *
 * The inventory's whole job is to let an operator answer one question at a
 * glance: **can I fix this, or does this need an engineer?** ADR-0030's lock has
 * two keys with two different owners —
 *
 *   - `enabled` — the *config* key. An operator owns it and can flip it from
 *     the panel after capturing acceptance-run evidence (ADR-0035 moved it out
 *     of the repo and into the database precisely so they could).
 *   - `acquisition_readiness` — the *code* key, three-state since #743. A
 *     `scaffold` needs a provider change, a review and a deploy. An
 *     `awaiting_evidence` provider is finished and only needs an acceptance run
 *     — which the operator dispatches themselves.
 *
 * Rendering both as two anonymous booleans would be honest but useless: an
 * operator staring at `false/false` cannot tell "capture evidence and turn it
 * on" from "file a ticket". `classifyTemplate` collapses the pair into the
 * decision the operator actually has to make.
 *
 * The code key used to dominate unconditionally, because a shut code key could
 * only mean "scaffold". That was wrong for every provider that was built but
 * unproven: the panel sent operators to an engineer to build something that
 * already existed. Now only `scaffold` is engineer-blocked; `awaiting_evidence`
 * is operator-actionable with a *different* first step (dispatch an acceptance
 * run, then flip the config key).
 *
 * Kept free of React so the classification is unit-testable without mounting
 * a table.
 */

import type { AcquisitionReadiness, SourceBlueprintTemplate } from "../lib/admin/dataProvider";
import type { PillLevel } from "../ui/primitives";

/**
 * What the operator can do about this template right now.
 *
 * - `live` — both keys turned; runs launch.
 * - `operator-actionable` — the provider is live and only the config key is
 *   shut. This is the pure-paperwork group: evidence, then flip.
 * - `awaiting-acceptance` — the provider is built but unproven. The operator's
 *   first step is dispatching an acceptance run, not filing a ticket.
 * - `engineer-blocked` — the provider is a scaffold. Flipping the config key
 *   changes nothing; the run still refuses on the provider.
 */
export type TemplateLockClass =
  | "live"
  | "operator-actionable"
  | "awaiting-acceptance"
  | "engineer-blocked";

export type LockClassDescriptor = {
  id: TemplateLockClass;
  /** Short column label. */
  label: string;
  /** One sentence naming the next action and who has to take it. */
  detail: string;
  level: PillLevel;
};

const LOCK_CLASSES: Record<TemplateLockClass, LockClassDescriptor> = {
  live: {
    id: "live",
    label: "Live",
    detail: "Both keys turned — live runs launch against this template.",
    level: "healthy",
  },
  "operator-actionable": {
    id: "operator-actionable",
    label: "Ready to enable",
    detail:
      "Provider is live; only the config key is shut. Capture acceptance-run " +
      "evidence, then enable it here — no engineer, no deploy.",
    level: "degraded",
  },
  "awaiting-acceptance": {
    id: "awaiting-acceptance",
    label: "Awaiting acceptance run",
    detail:
      "Provider is built and verified but has no acceptance evidence yet. Dispatch a run " +
      "with mode=acceptance against the live source, then enable it here — no engineer, " +
      "no deploy.",
    level: "degraded",
  },
  "engineer-blocked": {
    id: "engineer-blocked",
    label: "Needs provider work",
    detail:
      "The provider is a scaffold: start_run is not implemented, so it cannot acquire " +
      "anything yet. Enabling the config key will not unlock it — this needs a provider " +
      "change.",
    level: "critical",
  },
};

type LockLike = Pick<SourceBlueprintTemplate, "enabled" | "live_ready"> &
  Partial<Pick<SourceBlueprintTemplate, "acquisition_readiness">>;

/**
 * Resolve the code key, tolerating a payload that predates `acquisition_readiness`.
 *
 * The fallback maps the legacy boolean the way it was always meant: true means
 * live, false means scaffold. It must never invent `awaiting_evidence` — that
 * state is an assertion only the server can make.
 */
function readinessOf(template: LockLike): AcquisitionReadiness {
  return template.acquisition_readiness ?? (template.live_ready ? "live" : "scaffold");
}

export function classifyTemplate(template: LockLike): LockClassDescriptor {
  const readiness = readinessOf(template);
  if (readiness === "scaffold") {
    return LOCK_CLASSES["engineer-blocked"];
  }
  if (readiness === "awaiting_evidence") {
    return LOCK_CLASSES["awaiting-acceptance"];
  }
  return template.enabled ? LOCK_CLASSES.live : LOCK_CLASSES["operator-actionable"];
}

export const LOCK_CLASS_ORDER: TemplateLockClass[] = [
  "operator-actionable",
  "awaiting-acceptance",
  "engineer-blocked",
  "live",
];

export type InventorySummary = Record<TemplateLockClass, number> & { total: number };

export function summarizeInventory(templates: LockLike[]): InventorySummary {
  const summary: InventorySummary = {
    live: 0,
    "operator-actionable": 0,
    "awaiting-acceptance": 0,
    "engineer-blocked": 0,
    total: templates.length,
  };
  for (const template of templates) {
    summary[classifyTemplate(template).id] += 1;
  }
  return summary;
}

/**
 * Describe one key for the two-key column.
 *
 * `ownerHint` is the load-bearing half: it is what tells an operator whether
 * the shut key in front of them is theirs to turn.
 */
export type KeyDescriptor = {
  label: string;
  state: "open" | "shut";
  ownerHint: string;
  level: PillLevel;
};

export function describeConfigKey(template: LockLike): KeyDescriptor {
  return {
    label: "Config key",
    state: template.enabled ? "open" : "shut",
    ownerHint: template.enabled ? "on — an operator can turn this off" : "off — yours to turn",
    level: template.enabled ? "healthy" : "degraded",
  };
}

export function describeCodeKey(template: LockLike): KeyDescriptor {
  const readiness = readinessOf(template);
  if (readiness === "live") {
    return {
      label: "Code key",
      state: "open",
      ownerHint: "provider is live-ready",
      level: "healthy",
    };
  }
  if (readiness === "awaiting_evidence") {
    return {
      label: "Code key",
      state: "shut",
      // The ownerHint is the load-bearing half, and this is the case it used to
      // get wrong: the key is shut, but it is not an engineer's to turn (#743).
      ownerHint: "off — built, needs an acceptance run you can dispatch",
      level: "degraded",
    };
  }
  return {
    label: "Code key",
    state: "shut",
    ownerHint: "off — provider is a scaffold, needs an engineer",
    level: "critical",
  };
}

/**
 * Human sentence for the config key's provenance.
 *
 * Deliberately says "operator key", never a person's name. Attribution today is
 * key-shaped: every human sharing an operator API key resolves to the same
 * identity, so a UI that reads "flipped by Anna" would be asserting an
 * accountability the system cannot deliver.
 */
export function describeProvenance(
  template: Pick<SourceBlueprintTemplate, "source" | "default_enabled" | "updated_by">,
): string {
  if (template.source === "default") {
    return `Shipped default (${template.default_enabled ? "enabled" : "disabled"}) — never overridden.`;
  }
  return template.updated_by
    ? `Overridden by operator key ${template.updated_by}.`
    : "Overridden by an operator.";
}

/**
 * Describe the code key for the source-create preview panel.
 *
 * `SourceCreate` rendered `Code key (live_ready): off` for every shut code key,
 * which is the undifferentiated verdict #743 exists to remove — it reads the
 * same for a scaffold and for a provider that only needs an acceptance run.
 */
export function describeBlueprintCodeKey(lock: LockLike): { label: string; detail: string } {
  switch (readinessOf(lock)) {
    case "live":
      return { label: "on", detail: "The provider is live-ready." };
    case "awaiting_evidence":
      return {
        label: "awaiting acceptance run",
        detail:
          "The provider is built and verified. Capture evidence with the acceptance harness " +
          "(a run with mode=acceptance against the live source), then enable the template — " +
          "no engineer, no deploy.",
      };
    default:
      return {
        label: "off (scaffold)",
        detail:
          "The provider is a scaffold — start_run is not implemented. This needs engineering.",
      };
  }
}
