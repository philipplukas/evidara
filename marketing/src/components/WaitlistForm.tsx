"use client";

import { useId, useState } from "react";
import { HONEYPOT_FIELD, isValidEmail, submitWaitlist, type WaitlistResult } from "@/lib/waitlist";

type FormState = "idle" | "submitting" | WaitlistResult["status"];

export function WaitlistForm() {
  const emailId = useId();
  const roleId = useId();
  const honeypotId = useId();
  const statusId = useId();
  const errorId = useId();

  const [email, setEmail] = useState("");
  const [role, setRole] = useState("");
  const [honeypot, setHoneypot] = useState("");
  const [state, setState] = useState<FormState>("idle");
  const [message, setMessage] = useState("");
  // Only show the inline validation error after a submit attempt, so the
  // field does not scold someone who is still typing.
  const [showValidation, setShowValidation] = useState(false);

  const emailInvalid = showValidation && !isValidEmail(email);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setShowValidation(true);

    if (!isValidEmail(email)) {
      setState("idle");
      return;
    }

    setState("submitting");
    const result = await submitWaitlist({ email, role, honeypot });
    setState(result.status);
    setMessage(result.status === "error" ? result.message : "");
  }

  // A bot that tripped the honeypot is told the same thing a human is. It
  // learns nothing about why it failed.
  if (state === "ok" || state === "rejected") {
    return (
      <p
        // `role="status"` + `aria-live` so a screen reader announces the
        // outcome after the form is replaced, rather than silently swapping
        // the content out from under the user.
        role="status"
        aria-live="polite"
        className="rounded-[var(--marketing-radius-panel)] border border-[var(--border)] bg-[var(--surface-panel)] px-5 py-4 text-[var(--foreground)] shadow-[var(--shadow-card)]"
      >
        Thank you — we have your address. You will hear from us when there is something substantive
        to show.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label htmlFor={emailId} className="text-sm font-medium text-[var(--foreground)]">
          Email address
        </label>
        <input
          id={emailId}
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={emailInvalid}
          aria-describedby={emailInvalid ? errorId : undefined}
          placeholder="you@firm.example"
          className="min-h-[44px] rounded-[calc(var(--radius)*0.8)] border border-[var(--border)] bg-[var(--surface-input)] px-4 py-2.5 text-[var(--foreground)] placeholder:text-[var(--foreground-faint)] aria-[invalid=true]:border-[var(--status-critical)]"
        />
        {emailInvalid && (
          <p id={errorId} className="text-sm text-[var(--status-critical)]">
            Enter a valid email address.
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor={roleId} className="text-sm font-medium text-[var(--foreground)]">
          What you work on{" "}
          <span className="font-normal text-[var(--foreground-subtle)]">(optional)</span>
        </label>
        <input
          id={roleId}
          name="role"
          type="text"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          placeholder="Litigation, compliance, legal engineering…"
          className="min-h-[44px] rounded-[calc(var(--radius)*0.8)] border border-[var(--border)] bg-[var(--surface-input)] px-4 py-2.5 text-[var(--foreground)] placeholder:text-[var(--foreground-faint)]"
        />
      </div>

      {/*
        Honeypot. Hidden from sighted users by position (not `display: none`,
        which some bots detect) and from assistive tech by `aria-hidden` +
        `tabIndex={-1}`, so a screen-reader user never lands on it. A real
        person cannot fill this in; a naive bot fills every field it finds.
      */}
      <div aria-hidden="true" className="absolute left-[-9999px] h-px w-px overflow-hidden">
        <label htmlFor={honeypotId}>Company website</label>
        <input
          id={honeypotId}
          name={HONEYPOT_FIELD}
          type="text"
          tabIndex={-1}
          autoComplete="off"
          value={honeypot}
          onChange={(e) => setHoneypot(e.target.value)}
        />
      </div>

      <button
        type="submit"
        disabled={state === "submitting"}
        className="min-h-[44px] rounded-[calc(var(--radius)*0.8)] bg-[var(--accent-core)] px-6 py-2.5 font-[var(--font-weight-semibold)] text-[var(--accent-core-foreground)] shadow-[var(--shadow-ring-accent)] transition-opacity duration-[var(--motion-duration-short)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {state === "submitting" ? "Sending…" : "Join the waitlist"}
      </button>

      {/*
        Status region is always in the DOM so assistive tech has it registered
        before the text arrives — a live region inserted at the same moment as
        its content is unreliably announced.
      */}
      <p
        id={statusId}
        role="status"
        aria-live="polite"
        className="min-h-[1.25rem] text-sm text-[var(--foreground-muted)]"
      >
        {state === "not-configured" &&
          "Signups are not open yet — this form has no mailing list behind it so far. That is deliberate; see the note below."}
        {state === "error" && message}
      </p>

      <p className="text-sm text-[var(--foreground-subtle)]">
        One address, used to email you about Evidara and nothing else. No tracking pixels, no
        third-party analytics on this page.
      </p>
    </form>
  );
}
