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
 * Three deliberate properties:
 *
 * 1. **The evidence note is required to enable.** ADR-0030 calls this key the
 *    one an operator turns *after capturing acceptance-run evidence*. A flip
 *    with no recorded reason is indistinguishable from a flip made by guessing,
 *    and the whole lock exists to stop guessing. Disabling needs no note — you
 *    are closing the lock, which is always the safe direction.
 * 2. **Enabling a template whose code key is shut is not offered as a fix.** The
 *    dialog says so plainly rather than letting the operator turn a key that
 *    changes nothing and then meet a refusal at run time.
 * 3. **Attribution is described as key-shaped.** The audit column is
 *    `updated_by` and it records the *operator API key*, not a person — every
 *    human sharing that key resolves to one identity (`auth.py`). The copy says
 *    "operator key" so the panel never implies an accountability the system
 *    cannot deliver.
 */
"use client";

import { useState } from "react";
import { useNotify, useRefresh } from "react-admin";
import { controlPlaneActions, type SourceBlueprintTemplate } from "../../lib/admin/dataProvider";
import { Button, Dialog, FormField, InlineAlert } from "../../ui/primitives";

const NOTE_INPUT_CLASS =
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
  const [submitting, setSubmitting] = useState(false);

  if (!template) {
    return null;
  }

  const turningOn = !template.enabled;
  // Fall back to the legacy boolean for payloads that predate #743. Never infer
  // `awaiting_evidence` from it — only the server can assert that state.
  const codeKeyState =
    template.acquisition_readiness ?? (template.live_ready ? "live" : "scaffold");
  const noteRequired = turningOn;
  const noteMissing = noteRequired && note.trim().length === 0;

  const close = () => {
    setNote("");
    onClose();
  };

  const submit = async () => {
    if (noteMissing || submitting) {
      return;
    }
    setSubmitting(true);
    try {
      const result = await controlPlaneActions.setBlueprintTemplateEnablement(
        template.overlay_id,
        template.provider_template_id,
        { enabled: turningOn, note: note.trim() || null },
      );
      notify(
        result.enabled
          ? `Config key on for ${template.overlay_id}/${template.provider_template_id}.`
          : `Config key off for ${template.overlay_id}/${template.provider_template_id}.`,
        { type: "success" },
      );
      refresh();
      close();
    } catch (error) {
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
            that request, and paste it here as your evidence note.
          </InlineAlert>
        ) : null}

        {turningOn ? (
          <InlineAlert tone="info">
            <strong>Evidence gate.</strong> ADR-0030 gates this key on acceptance-run evidence, not
            on confidence. Record what you ran and what it produced — the note is the only durable
            record of why this template was trusted.
          </InlineAlert>
        ) : (
          <InlineAlert tone="warning">
            <strong>Runs will be refused.</strong> New live runs against this template will be
            rejected by the two-key lock as soon as the key closes. Runs already in flight are
            unaffected.
          </InlineAlert>
        )}

        <FormField
          id="blueprint-enablement-note"
          label="Evidence note"
          required={noteRequired}
          helperText={
            noteRequired
              ? "Required. E.g. 'acceptance run r_01J… 2026-07-19: 42/42 acts parsed, spot-checked 5 against the portal'."
              : "Optional — why the key is being closed."
          }
          error={noteMissing && note.length > 0 ? "An evidence note is required to enable." : null}
        >
          <textarea
            id="blueprint-enablement-note"
            rows={3}
            value={note}
            disabled={submitting}
            onChange={(event) => setNote(event.target.value)}
            className={NOTE_INPUT_CLASS}
            placeholder={
              noteRequired ? "Acceptance run id, date, and what it proved" : "Reason for disabling"
            }
          />
        </FormField>

        <p className="text-[12px] text-[var(--foreground-subtle)]">
          Recorded against the <strong>operator API key</strong> you are authenticated with, not
          against you personally — everyone sharing a key writes the same <code>updated_by</code>.
        </p>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
        <Button variant="secondary" onClick={close} disabled={submitting}>
          Cancel
        </Button>
        <Button variant="primary" onClick={submit} disabled={noteMissing || submitting}>
          {submitting ? "Saving…" : turningOn ? "Enable template" : "Disable template"}
        </Button>
      </div>
    </Dialog>
  );
}
