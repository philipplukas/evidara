/**
 * `TextInput` — single-line / multiline text input bound to `ra-core`'s
 * `useInput`. Spreads `field` onto a native `<input>` / `<textarea>`, so
 * validation, dirty tracking, submit blocking, and `defaultValues` from
 * `<Form record={...}>` all work identically to react-admin's MUI
 * `<TextInput>` — no MUI dependency.
 */
"use client";

import { useInput, useTranslate, type Validator } from "ra-core";
import { useId } from "react";
import { cn } from "./cn";
import { FormField } from "./FormField";
import { translateValidationError } from "./validationError";

interface TextInputProps {
  source: string;
  label: string;
  description?: React.ReactNode;
  helperText?: React.ReactNode;
  multiline?: boolean;
  rows?: number;
  disabled?: boolean;
  required?: boolean;
  validate?: Validator | Validator[];
  placeholder?: string;
  /** Extra classes for the input/textarea element. */
  inputClassName?: string;
}

const BASE_INPUT =
  "w-full rounded-lg border bg-[var(--surface-input)] px-3 py-2.5 text-sm text-[var(--foreground)] " +
  "placeholder:text-[var(--foreground-subtle)] shadow-[var(--shadow-inset-surface)] " +
  "transition-[border-color,box-shadow] " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const BORDER_OK = "border-[var(--border)] hover:border-[var(--accent-core)]/30";
const BORDER_ERROR = "border-[var(--status-critical)] hover:border-[var(--status-critical)]";

export function TextInput({
  source,
  label,
  description,
  helperText,
  multiline,
  rows = 3,
  disabled,
  required,
  validate,
  placeholder,
  inputClassName,
}: TextInputProps) {
  const id = useId();
  const translate = useTranslate();
  const { field, fieldState, isRequired } = useInput({
    source,
    validate,
  });
  const errorMessage =
    // Unwrap ra-core's "@@react-admin@@" validator envelope and translate it,
    // instead of showing the operator a raw i18n key (#671).
    translateValidationError(translate, fieldState.error?.message);
  const effectivelyRequired = required ?? isRequired;
  const commonClassName = cn(BASE_INPUT, errorMessage ? BORDER_ERROR : BORDER_OK, inputClassName);

  return (
    <FormField
      id={id}
      label={label}
      required={effectivelyRequired}
      description={description}
      helperText={helperText}
      error={errorMessage}
    >
      {multiline ? (
        <textarea
          {...field}
          id={id}
          rows={rows}
          disabled={disabled}
          placeholder={placeholder}
          aria-invalid={!!errorMessage}
          aria-required={effectivelyRequired || undefined}
          className={cn(commonClassName, "resize-y leading-snug")}
          value={field.value ?? ""}
        />
      ) : (
        <input
          {...field}
          id={id}
          type="text"
          disabled={disabled}
          placeholder={placeholder}
          aria-invalid={!!errorMessage}
          aria-required={effectivelyRequired || undefined}
          className={commonClassName}
          value={field.value ?? ""}
        />
      )}
    </FormField>
  );
}
