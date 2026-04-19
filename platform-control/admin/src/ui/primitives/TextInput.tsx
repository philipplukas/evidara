/**
 * `TextInput` — single-line / multiline text input bound to `ra-core`'s
 * `useInput`. Spreads `field` onto a native `<input>` / `<textarea>`, so
 * validation, dirty tracking, submit blocking, and `defaultValues` from
 * `<Form record={...}>` all work identically to react-admin's MUI
 * `<TextInput>` — no MUI dependency.
 */
"use client";

import { useInput, type Validator } from "ra-core";
import { useId } from "react";
import { cn } from "./cn";
import { FormField } from "./FormField";

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
  "w-full rounded-xl border bg-white/85 px-3 py-2.5 text-sm text-[#1d293d] " +
  "placeholder:text-[rgba(29,41,61,0.35)] " +
  "transition-[border-color,box-shadow] " +
  "focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-[rgba(15,76,129,0.42)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const BORDER_OK = "border-[rgba(29,41,61,0.16)] hover:border-[rgba(29,41,61,0.28)]";
const BORDER_ERROR = "border-[#b71c1c] hover:border-[#b71c1c]";

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
  const { field, fieldState, isRequired } = useInput({
    source,
    validate,
  });
  const errorMessage =
    typeof fieldState.error?.message === "string" ? fieldState.error.message : null;
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
