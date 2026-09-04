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
 *   shut, and *nobody ever turned it*. This is the pure-paperwork group:
 *   evidence, then flip.
 * - `operator-disabled` — somebody turned the config key off on purpose. This
 *   is a different state with a different first step (ask them), and it used to
 *   be collapsed into `operator-actionable` because the class was derived from
 *   `enabled` alone. Both read `enabled: false`; only `source` separates them,
 *   and the difference is load-bearing everywhere else in the platform —
 *   ADR-0030's acceptance waiver dispatches at a never-turned key and refuses
 *   at a kill switch (#768), and the flip guard refuses to reopen one without
 *   an explicit acknowledgement (#854).
 * - `awaiting-acceptance` — the provider is built but unproven. The operator's
 *   first step is dispatching an acceptance run, not filing a ticket.
 * - `engineer-blocked` — the provider is a scaffold. Flipping the config key
 *   changes nothing; the run still refuses on the provider.
 */
export type TemplateLockClass =
  | "live"
  | "operator-actionable"
  | "operator-disabled"
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
      "Provider is live; only the config key is shut, and nobody has turned it. " +
      "Capture acceptance-run evidence, then enable it here — no engineer, no deploy.",
    level: "degraded",
  },
  "operator-disabled": {
    id: "operator-disabled",
    label: "Turned off by an operator",
    detail:
      "Somebody deliberately shut the config key — a kill switch, not a key that was " +
      "never earned. Acceptance mode does not waive it, and reopening it needs an " +
      "explicit acknowledgement. Read the note, and ask them first.",
    level: "critical",
  },
  "awaiting-acceptance": {
    id: "awaiting-acceptance",
    label: "Awaiting acceptance run",
    detail:
      "Provider is built and verified but has no acceptance evidence yet. Capture it " +
      "yourself with the acceptance harness (a run with mode=acceptance against the live " +
      "source). Going live afterwards still needs a code change to move the provider to " +
      "'live' — attach your evidence to that request.",
    level: "degraded",
  },
  "engineer-blocked": {
    id: "engineer-blocked",
    label: "Needs provider work",
    detail:
      "The provider cannot acquire its targets yet — either start_run is a stub, or it " +
      "faces sources it cannot fetch. Enabling the config key will not unlock it; this " +
      "needs a provider change.",
    level: "critical",
  },
};

type LockLike = Pick<SourceBlueprintTemplate, "enabled" | "live_ready"> &
  Partial<Pick<SourceBlueprintTemplate, "acquisition_readiness" | "source">>;

/**
 * Whether the config key's current value is an operator's deliberate act.
 *
 * `source` is the provenance the API has published since #632: `"override"` means a
 * row in `blueprint_template_overrides`, `"default"` means the shipped
 * `source_blueprints.yaml` value nobody has touched. A payload that predates the field
 * is read as `default` — the safe direction, because inventing a kill switch nobody
 * installed would tell an operator to go ask a colleague who does not exist.
 */
function isOperatorOverride(template: LockLike): boolean {
  return template.source === "override";
}

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

/**
 * The priority order mirrors `evidara_cli.coverage.classify_template`'s blocker
 * ordering — scaffold, then an operator's kill switch, then awaiting evidence — so the
 * panel and the CLI never disagree about what the first step is. The kill switch is
 * *also* surfaced unconditionally by {@link describeConfigKey}, because at a scaffold
 * provider this class reports "needs provider work" and the closed key would otherwise
 * stay invisible behind it (#854).
 */
export function classifyTemplate(template: LockLike): LockClassDescriptor {
  const readiness = readinessOf(template);
  if (readiness === "scaffold") {
    return LOCK_CLASSES["engineer-blocked"];
  }
  if (!template.enabled && isOperatorOverride(template)) {
    return LOCK_CLASSES["operator-disabled"];
  }
  if (readiness === "awaiting_evidence") {
    return LOCK_CLASSES["awaiting-acceptance"];
  }
  return template.enabled ? LOCK_CLASSES.live : LOCK_CLASSES["operator-actionable"];
}

/**
 * How prominent the row's enable/disable control is allowed to be, and what it
 * must admit about itself.
 *
 * The inventory rendered a filled violet `Enable` — the page's strongest visual
 * commitment — on every unenabled row, including the rows whose own Status cell
 * reads "Enabling the config key will not unlock it; this needs a provider
 * change." The most prominent affordance on the row was the futile one.
 *
 * The truth this encodes is `SourceService`'s: `launchable = enabled and
 * live_ready` (`services/source_service.py`). Where the code key is shut,
 * turning the config key changes `enabled` and nothing an operator wants —
 * runs still refuse. That is not a reason to *hide* the control (a template
 * can be pre-enabled ahead of a provider landing, and the enablement dialog
 * carries its own code-key warning), but it is a reason to stop presenting it
 * as the obvious next step.
 *
 * Deliberately NOT modelled here: whether the flip is permitted at all. The
 * enablement guard is #854's, and a second opinion about it living in the UI is
 * how two guards drift apart.
 */
export type EnablementAction = {
  label: "Enable" | "Disable";
  /** Maps to the `Button` primitive's variant. */
  variant: "primary" | "secondary" | "ghost";
  /**
   * One clause naming what the action will not achieve, or `null` when it will
   * achieve exactly what its label says. Rendered beside the control.
   */
  futility: string | null;
};

export function describeEnablementAction(template: LockLike): EnablementAction {
  if (template.enabled) {
    // Turning a key off always does what it says, whatever the provider is
    // doing — including on a scaffold, where it is the only way to undo a
    // premature flip.
    return { label: "Disable", variant: "secondary", futility: null };
  }

  switch (readinessOf(template)) {
    case "live":
      // The one case where enabling is the next step and finishes the job.
      return { label: "Enable", variant: "primary", futility: null };
    case "awaiting_evidence":
      return {
        label: "Enable",
        variant: "ghost",
        futility: "Will not launch runs yet — the code key is still shut.",
      };
    default:
      return {
        label: "Enable",
        variant: "ghost",
        futility: "Will not launch runs — the provider needs a change first.",
      };
  }
}

export const LOCK_CLASS_ORDER: TemplateLockClass[] = [
  "operator-actionable",
  "awaiting-acceptance",
  "operator-disabled",
  "engineer-blocked",
  "live",
];

export type InventorySummary = Record<TemplateLockClass, number> & { total: number };

export function summarizeInventory(templates: LockLike[]): InventorySummary {
  const summary: InventorySummary = {
    live: 0,
    "operator-actionable": 0,
    "operator-disabled": 0,
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
  if (template.enabled) {
    return {
      label: "Config key",
      state: "open",
      ownerHint: "on — an operator can turn this off",
      level: "healthy",
    };
  }
  // Said unconditionally, because this is the state the dialog is about to overwrite
  // and it must be legible before the operator opens it. `classifyTemplate` reports
  // "needs provider work" for a kill switch on a scaffold provider, so the class
  // column alone cannot be where a kill switch becomes visible (#854).
  if (isOperatorOverride(template)) {
    return {
      label: "Config key",
      state: "shut",
      ownerHint: "off — an operator shut this deliberately; ask before reopening",
      level: "critical",
    };
  }
  return {
    label: "Config key",
    state: "shut",
    ownerHint: "off — never turned; yours to turn",
    level: "degraded",
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
      ownerHint: "off — built; capture evidence with the harness, then a code change",
      level: "degraded",
    };
  }
  return {
    label: "Code key",
    state: "shut",
    ownerHint: "off — provider cannot acquire its targets, needs an engineer",
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
          "(a run with mode=acceptance against the live source). Moving the provider to " +
          "'live' afterwards is a code change — attach the evidence to that request.",
      };
    default:
      return {
        label: "off (scaffold)",
        detail: "The provider cannot acquire its targets yet. This needs engineering.",
      };
  }
}
