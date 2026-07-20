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
 *   - `live_ready` — the *code* key. It is the provider class asserting it can
 *     physically acquire this format. No operator action can open it; it takes
 *     a provider change, a review and a deploy.
 *
 * Rendering both as two anonymous booleans would be honest but useless: an
 * operator staring at `false/false` cannot tell "capture evidence and turn it
 * on" from "file a ticket". `classifyTemplate` collapses the pair into the
 * decision the operator actually has to make, and the code key dominates —
 * a template whose provider is a scaffold is *not* operator-actionable even
 * when its config key is the only thing shut on paper.
 *
 * Kept free of React so the classification is unit-testable without mounting
 * a table.
 */

import type { SourceBlueprintTemplate } from "../lib/admin/dataProvider";
import type { PillLevel } from "../ui/primitives";

/**
 * What the operator can do about this template right now.
 *
 * - `live` — both keys turned; runs launch.
 * - `operator-actionable` — the provider is ready and only the config key is
 *   shut. This is the pure-paperwork group: evidence, then flip.
 * - `engineer-blocked` — the code key is shut. Flipping the config key changes
 *   nothing; the run still refuses on the provider.
 */
export type TemplateLockClass = "live" | "operator-actionable" | "engineer-blocked";

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
    label: "Awaiting evidence",
    detail:
      "Provider is live-ready; only the config key is shut. Capture acceptance-run " +
      "evidence, then enable it here — no engineer, no deploy.",
    level: "degraded",
  },
  "engineer-blocked": {
    id: "engineer-blocked",
    label: "Needs provider work",
    detail:
      "The code key is shut: the provider cannot yet acquire this format. Enabling the " +
      "config key will not unlock it — this needs a provider change.",
    level: "critical",
  },
};

type LockLike = Pick<SourceBlueprintTemplate, "enabled" | "live_ready">;

export function classifyTemplate(template: LockLike): LockClassDescriptor {
  if (!template.live_ready) {
    return LOCK_CLASSES["engineer-blocked"];
  }
  return template.enabled ? LOCK_CLASSES.live : LOCK_CLASSES["operator-actionable"];
}

export const LOCK_CLASS_ORDER: TemplateLockClass[] = [
  "operator-actionable",
  "engineer-blocked",
  "live",
];

export type InventorySummary = Record<TemplateLockClass, number> & { total: number };

export function summarizeInventory(templates: LockLike[]): InventorySummary {
  const summary: InventorySummary = {
    live: 0,
    "operator-actionable": 0,
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
  return {
    label: "Code key",
    state: template.live_ready ? "open" : "shut",
    ownerHint: template.live_ready
      ? "provider is live-ready"
      : "off — provider code, needs an engineer",
    level: template.live_ready ? "healthy" : "critical",
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
