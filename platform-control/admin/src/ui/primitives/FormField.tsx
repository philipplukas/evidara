/**
 * `FormField` — label + optional description + child input + error +
 * helper-text wrapper. UI-only; it does not own any form state. Pair with
 * `TextInput` (or any future input primitive) which binds via `useInput`.
 *
 * The required marker is rendered as a sibling of `<label>` so the label's
 * accessible name stays unambiguously equal to `label` — some a11y tools
 * concatenate aria-hidden children into the accessible name.
 */
"use client";

import type { ReactNode } from "react";
import { cn } from "./cn";

interface FormFieldProps {
  id: string;
  label: string;
  required?: boolean;
  description?: ReactNode;
  helperText?: ReactNode;
  error?: string | null;
  children: ReactNode;
  className?: string;
}

export function FormField({
  id,
  label,
  required,
  description,
  helperText,
  error,
  children,
  className,
}: FormFieldProps) {
  const describedBy: string[] = [];
  if (error) describedBy.push(`${id}-error`);
  if (helperText) describedBy.push(`${id}-helper`);

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {/*
       * Required marker is rendered as a sibling of the `<label>`, not a
       * child, so the label's accessible name stays unambiguously equal
       * to `label` — otherwise tools (and `page.getByLabel` in tests) can
       * concatenate the asterisk into the accessible name even with
       * `aria-hidden`.
       */}
      <div className="inline-flex items-baseline gap-1">
        <label
          htmlFor={id}
          className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-meta)] leading-[1.2]"
        >
          {label}
        </label>
        {required ? (
          <span
            aria-hidden
            className="text-[var(--status-critical)] text-[11px] font-semibold leading-[1.2]"
          >
            *
          </span>
        ) : null}
      </div>
      {description ? (
        <p className="text-[12px] text-[var(--text-meta)] leading-snug">{description}</p>
      ) : null}
      <div data-described-by={describedBy.join(" ") || undefined}>{children}</div>
      {error ? (
        <p id={`${id}-error`} className="text-[12px] text-[var(--status-critical)] font-medium">
          {error}
        </p>
      ) : null}
      {helperText && !error ? (
        <p id={`${id}-helper`} className="text-[12px] text-[var(--muted-foreground)]">
          {helperText}
        </p>
      ) : null}
    </div>
  );
}
