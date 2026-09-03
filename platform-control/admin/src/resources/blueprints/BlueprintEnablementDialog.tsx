/**
 * `BlueprintEnablementDialog` — the operator's hand on the ADR-0030 config key.
 *
 * Before #668 this action existed only as `setBlueprintTemplateEnablement` in
 * the dataProvider with **zero callers**: the panel rendered the lock, told the
 * operator the template was inert, and then instructed them to issue
 * `PUT .../enablement` by hand. That is an engineer with `curl`, which is the
 * exact cost ADR-0033/#628 exists to drive to zero. This dialog is the missing
 * control.
 *
 * ## What #854 changed
 *
 * Until then the entire precondition for arming the key was **a non-empty
 * free-text note**. `evidara workflow coverage enable` (#832), for the identical
 * operation, required a cited acceptance run, re-derived the acceptance verdict,
 * checked provider readiness, demanded an explicit acknowledgement to reopen an
 * operator's kill switch, and refused with eight named codes. So the two paths to
 * the same state differed sharply in rigour and **the easier one was the weaker
 * one** — an operator refused by the CLI could get the same result by typing one
 * character here. That made the CLI's guard advisory rather than enforced, and a
 * free-text note is not evidence; it is a comment.
 *
 * The fix was not to port the CLI's checks into this component — that would have
 * been a third copy of a rule the codebase already warns exists twice. The guard
 * moved into `BlueprintEnablementService` behind the same endpoint both clients
 * call, and this dialog's job is now to **collect the guard's inputs and render
 * its refusal codes**. Nothing here decides whether a flip is allowed.
 *
 * Three properties that survive from the original:
 *
 * 1. **Enabling a template whose code key is shut is not offered as a fix.** The
 *    dialog says so plainly rather than letting the operator turn a key that
 *    changes nothing and then meet a refusal at run time.
 * 2. **Attribution is described as key-shaped.** The audit column is
 *    `updated_by` and it records the *operator API key*, not a person — every
 *    human sharing that key resolves to one identity (`auth.py`). The copy says
 *    "operator key" so the panel never implies an accountability the system
 *    cannot deliver.
 * 3. **The note is required**, now in both directions and enforced server-side:
 *    shutting a portal off with no recorded reason is as unauditable as arming
 *    one.
 */
"use client";

import { useState } from "react";
import { useNotify, useRefresh } from "react-admin";
import {
  type BlueprintEnablementRefusal,
  blueprintEnablementRefusals,
  controlPlaneActions,
  type SourceBlueprintTemplate,
} from "../../lib/admin/dataProvider";
import { Button, Checkbox, Dialog, FormField, InlineAlert } from "../../ui/primitives";

const INPUT_CLASS =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--surface-input)] " +
  "px-3 py-2.5 text-sm text-[var(--foreground)] shadow-[var(--shadow-inset-surface)] " +
  "placeholder:text-[var(--foreground-subtle)] transition-[border-color,box-shadow] " +
  "hover:border-[var(--accent-core)]/30 " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

interface BlueprintEnablementDialogProps {
  template: SourceBlueprintTemplate | null;
  onClose: () => void;
}

export function BlueprintEnablementDialog({ template, onClose }: BlueprintEnablementDialogProps) {
  const notify = useNotify();
  const refresh = useRefresh();
  const [note, setNote] = useState("");
  const [evidenceRunId, setEvidenceRunId] = useState("");
  const [reopenKillSwitch, setReopenKillSwitch] = useState(false);
  const [acknowledgeBelowLive, setAcknowledgeBelowLive] = useState(false);
  const [refusals, setRefusals] = useState<BlueprintEnablementRefusal[]>([]);
  const [submitting, setSubmitting] = useState(false);

  if (!template) {
    return null;
  }

  const turningOn = !template.enabled;
  // Fall back to the legacy boolean for payloads that predate #743. Never infer
  // `awaiting_evidence` from it — only the server can assert that state.
  const codeKeyState =
    template.acquisition_readiness ?? (template.live_ready ? "live" : "scaffold");
  // An operator's deliberate kill switch, not a key that was never earned (#768).
  const isKillSwitch = !template.enabled && template.source === "override";
  const noteMissing = note.trim().length === 0;
  const evidenceMissing = turningOn && evidenceRunId.trim().length === 0;
  const canSubmit = !noteMissing && !evidenceMissing && !submitting;

  const close = () => {
    setNote("");
    setEvidenceRunId("");
    setReopenKillSwitch(false);
    setAcknowledgeBelowLive(false);
    setRefusals([]);
    onClose();
  };

  const submit = async () => {
    if (!canSubmit) {
      return;
    }
    setSubmitting(true);
    setRefusals([]);
    try {
      const result = await controlPlaneActions.setBlueprintTemplateEnablement(
        template.overlay_id,
        template.provider_template_id,
        {
          enabled: turningOn,
          note: note.trim(),
          evidence_run_id: turningOn ? evidenceRunId.trim() : null,
          reopen_operator_kill_switch: reopenKillSwitch,
          acknowledge_provider_below_live: acknowledgeBelowLive,
        },
      );
      // `applied` is the server's own read-back, not the status code. A 200 alone
      // cannot tell a flip from a write that silently did nothing (#631, #713).
      if (!result.applied) {
        setRefusals([
          {
            code: "read_back_disagrees",
            detail:
              "The request was accepted but re-reading the template does not confirm " +
              "the new key. Do not treat this template as flipped — check the " +
              "Blueprints list before doing anything that depends on it.",
          },
        ]);
        return;
      }
      const target = `${template.overlay_id}/${template.provider_template_id}`;
      notify(result.enabled ? `Config key on for ${target}.` : `Config key off for ${target}.`, {
        type: result.needs_human ? "warning" : "success",
      });
      for (const reason of result.needs_human_reasons) {
        notify(reason, { type: "warning" });
      }
      refresh();
      close();
    } catch (error) {
      // Refusals arrive as a 409 with machine-readable codes. Rendering a generic
      // "could not change the config key" would throw away the only part of the
      // answer that says what to do next (#854).
      const codes = blueprintEnablementRefusals(error);
      if (codes.length > 0) {
        setRefusals(codes);
        return;
      }
      notify(
        `Could not change the config key: ${error instanceof Error ? error.message : String(error)}`,
        { type: "error" },
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open
      onClose={close}
      dismissable={!submitting}
      size="md"
      testId="blueprint-enablement-dialog"
      title={turningOn ? "Turn the config key on" : "Turn the config key off"}
      description={`${template.overlay_id} · ${template.provider_template_id} · provider ${template.provider}`}
    >
      <div className="space-y-4">
        {refusals.length > 0 ? (
          <InlineAlert tone="error" testId="blueprint-enablement-refusals">
            <strong>
              {refusals.some((item) => item.code === "read_back_disagrees")
                ? "The key may not have moved."
                : "Refused — nothing was written."}
            </strong>
            <ul className="mt-2 space-y-2">
              {refusals.map((item) => (
                <li key={item.code}>
                  <code className="text-[12px] font-semibold">{item.code}</code>
                  <span className="block text-[12px]">{item.detail}</span>
                </li>
              ))}
            </ul>
          </InlineAlert>
        ) : null}

        {isKillSwitch ? (
          <InlineAlert tone="error" testId="blueprint-enablement-kill-switch-warning">
            <strong>An operator turned this key off deliberately.</strong> This is a kill switch,
            not a key that was never earned — acceptance mode does not waive it, and reopening it
            needs the acknowledgement below.
            {template.note ? <span className="block mt-1 italic">“{template.note}”</span> : null}
            {template.updated_by ? (
              <span className="block mt-1">
                Shut by operator key <code>{template.updated_by}</code>. Ask them first.
              </span>
            ) : null}
          </InlineAlert>
        ) : null}

        {turningOn && codeKeyState === "scaffold" ? (
          <InlineAlert tone="error" testId="blueprint-enablement-code-key-warning">
            <strong>This will not make the template launchable.</strong> The code key is shut —
            provider <code>{template.provider}</code> cannot acquire its targets yet — either
            start_run is a stub, or it faces sources it cannot fetch. Turning the config key on
            records your intent, but live runs stay blocked until the provider ships. That half
            needs an engineer.
          </InlineAlert>
        ) : null}

        {turningOn && codeKeyState === "awaiting_evidence" ? (
          <InlineAlert tone="warning" testId="blueprint-enablement-acceptance-warning">
            <strong>Capture an acceptance run first.</strong> Provider{" "}
            <code>{template.provider}</code> is built and verified, but no acceptance evidence has
            been captured for this template. Run the acceptance harness against the live source (a
            run with <code>mode=acceptance</code>) — you can do that yourself. Note that moving the
            provider to <code>live</code> afterwards is still a code change; attach your verdict to
            that request, and cite the run id below.
          </InlineAlert>
        ) : null}

        {turningOn ? (
          <InlineAlert tone="info">
            <strong>Evidence gate.</strong> ADR-0030 gates this key on acceptance-run evidence, not
            on confidence. platform-control re-derives the verdict from the run you cite and refuses
            if it does not earn the flip — a run that was refused by the lock, did not complete, ran
            in another mode, replayed fixtures (<code>execution_mode: shadow</code>), captured
            nothing, or belongs to a different template.
          </InlineAlert>
        ) : (
          <InlineAlert tone="warning">
            <strong>Runs will be refused.</strong> New live runs against this template will be
            rejected by the two-key lock as soon as the key closes. Runs already in flight are
            unaffected.
          </InlineAlert>
        )}

        {turningOn ? (
          <FormField
            id="blueprint-enablement-evidence-run"
            label="Acceptance run id"
            required
            helperText="The run whose evidence earns this flip — e.g. run_01J…. The server re-derives its verdict and checks it belongs to this template."
            error={
              evidenceMissing && evidenceRunId.length > 0
                ? "An acceptance run id is required to enable."
                : null
            }
          >
            <input
              id="blueprint-enablement-evidence-run"
              type="text"
              value={evidenceRunId}
              disabled={submitting}
              onChange={(event) => setEvidenceRunId(event.target.value)}
              className={INPUT_CLASS}
              placeholder="run_01J…"
            />
          </FormField>
        ) : null}

        <FormField
          id="blueprint-enablement-note"
          label="Evidence note"
          required
          helperText={
            turningOn
              ? "Required. E.g. 'evidence bundle docs/runbooks/evidence/2026-07-28-…: 42/42 acts parsed, spot-checked 5 against the portal'."
              : "Required — why the key is being closed. Somebody will read this before reopening it."
          }
          error={noteMissing && note.length > 0 ? "A note is required." : null}
        >
          <textarea
            id="blueprint-enablement-note"
            rows={3}
            value={note}
            disabled={submitting}
            onChange={(event) => setNote(event.target.value)}
            className={INPUT_CLASS}
            placeholder={
              turningOn ? "Evidence bundle path, date, and what it proved" : "Reason for disabling"
            }
          />
        </FormField>

        {turningOn && isKillSwitch ? (
          <Checkbox
            checked={reopenKillSwitch}
            onCheckedChange={setReopenKillSwitch}
            disabled={submitting}
            label="Reopen the operator's kill switch"
            description="I have asked the operator who shut this key, and they agreed to reopen it."
          />
        ) : null}

        {turningOn && codeKeyState !== "live" ? (
          <Checkbox
            checked={acknowledgeBelowLive}
            onCheckedChange={setAcknowledgeBelowLive}
            disabled={submitting}
            label="Arm the key ahead of the code key"
            description={`ADR-0030 §2 wants the provider at 'live' first; this one is '${codeKeyState}'. The lock still refuses production runs meanwhile, so the harm is deferred, not absent.`}
          />
        ) : null}

        <p className="text-[12px] text-[var(--foreground-subtle)]">
          Recorded against the <strong>operator API key</strong> you are authenticated with, not
          against you personally — everyone sharing a key writes the same <code>updated_by</code>.
        </p>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
        <Button variant="secondary" onClick={close} disabled={submitting}>
          Cancel
        </Button>
        <Button variant="primary" onClick={submit} disabled={!canSubmit}>
          {submitting ? "Saving…" : turningOn ? "Enable template" : "Disable template"}
        </Button>
      </div>
    </Dialog>
  );
}
