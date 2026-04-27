/**
 * `Select` — headless dropdown bound to `ra-core`'s `useInput`, rendered on
 * top of `@radix-ui/react-select`. Mirrors `TextInput.tsx` end-to-end: same
 * label + description + error/helper cascade via `FormField`, same focus
 * ring, same border treatment, same error state. The `field.onChange` from
 * `useInput` is wired to radix's `onValueChange`, so react-hook-form dirty
 * tracking, validation, and `<Form sanitizeEmptyValues>` all behave the
 * same way `<TextInput>` does.
 *
 * Radix portals the listbox to `document.body`; keyboard nav (Up/Down/Home/
 * End/Enter/Escape), typeahead, and `aria-activedescendant` come for free.
 * When `allowEmpty` is true, the caller-controlled `emptyLabel` renders as
 * the first item with a sentinel value and gets translated back to `null`
 * inside `onValueChange` — radix doesn't allow an empty-string item value,
 * so we route it through a local constant (`EMPTY_SENTINEL`).
 */
"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { useInput, type Validator } from "ra-core";
import { useId } from "react";
import { cn } from "./cn";
import { FormField } from "./FormField";

export interface SelectChoice {
  id: string;
  name: string;
}

interface SelectProps {
  source: string;
  label: string;
  choices: SelectChoice[];
  description?: React.ReactNode;
  helperText?: React.ReactNode;
  disabled?: boolean;
  required?: boolean;
  validate?: Validator | Validator[];
  placeholder?: string;
  /** When true, render an "empty" first item that resolves to `null`. */
  allowEmpty?: boolean;
  emptyLabel?: string;
  /** Extra classes for the trigger button. */
  triggerClassName?: string;
}

const BASE_TRIGGER =
  "inline-flex w-full items-center justify-between gap-2 rounded-lg border bg-[var(--surface-input)] " +
  "px-3 py-2.5 text-sm text-[var(--foreground)] " +
  "shadow-[var(--shadow-inset-surface)] transition-[border-color,box-shadow] " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed " +
  // `[&>span]:truncate` keeps long choice labels from blowing past the trigger width.
  "[&>span:first-child]:truncate [&>span:first-child]:text-left [&>span:first-child]:flex-1";

const BORDER_OK = "border-[var(--border)] hover:border-[var(--accent-core)]/30";
const BORDER_ERROR = "border-[var(--status-critical)] hover:border-[var(--status-critical)]";

const CONTENT_CLASS =
  "z-50 min-w-[var(--radix-select-trigger-width)] max-h-[320px] overflow-hidden " +
  "rounded-lg border border-[var(--border)] bg-[var(--surface-panel)] text-[var(--foreground)] " +
  "shadow-[var(--shadow-card)] " +
  "data-[state=open]:animate-in data-[state=closed]:animate-out " +
  "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0";

const ITEM_CLASS =
  "relative flex w-full cursor-pointer select-none items-center gap-2 " +
  "rounded-lg px-2.5 py-2 text-sm text-[var(--foreground)] outline-none " +
  "data-[highlighted]:bg-[var(--interactive-accent-subtle)] data-[highlighted]:text-[var(--accent-core)] " +
  "data-[state=checked]:font-semibold data-[state=checked]:text-[var(--accent-core)] " +
  "data-[disabled]:opacity-50 data-[disabled]:cursor-not-allowed";

// Radix forbids the empty string as an item value. We round-trip the
// "no selection" state through a local sentinel so consumers still get
// `null` on the form, matching the old MUI `SelectInput`'s `parse(empty→null)`.
const EMPTY_SENTINEL = "__empty__";

export function Select({
  source,
  label,
  choices,
  description,
  helperText,
  disabled,
  required,
  validate,
  placeholder = "Select…",
  allowEmpty,
  emptyLabel = "None",
  triggerClassName,
}: SelectProps) {
  const id = useId();
  const { field, fieldState, isRequired } = useInput({
    source,
    validate,
  });
  const errorMessage =
    typeof fieldState.error?.message === "string" ? fieldState.error.message : null;
  const effectivelyRequired = required ?? isRequired;

  // Convert radix's string-only value domain into the ra-core field value:
  //  - EMPTY_SENTINEL → null  (emptied selection when `allowEmpty`)
  //  - anything else   → itself (choice id)
  const handleValueChange = (next: string) => {
    field.onChange(next === EMPTY_SENTINEL ? null : next);
  };

  const radixValue =
    field.value === null || field.value === undefined || field.value === ""
      ? allowEmpty
        ? EMPTY_SENTINEL
        : ""
      : String(field.value);

  return (
    <FormField
      id={id}
      label={label}
      required={effectivelyRequired}
      description={description}
      helperText={helperText}
      error={errorMessage}
    >
      <SelectPrimitive.Root
        value={radixValue}
        onValueChange={handleValueChange}
        disabled={disabled}
        name={field.name}
      >
        <SelectPrimitive.Trigger
          id={id}
          ref={field.ref}
          onBlur={field.onBlur}
          aria-invalid={!!errorMessage}
          aria-required={effectivelyRequired || undefined}
          className={cn(BASE_TRIGGER, errorMessage ? BORDER_ERROR : BORDER_OK, triggerClassName)}
        >
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon aria-hidden>
            <ChevronDown size={16} className="text-[var(--foreground-subtle)]" />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content position="popper" sideOffset={6} className={CONTENT_CLASS}>
            <SelectPrimitive.Viewport className="p-1.5">
              {allowEmpty ? (
                <SelectPrimitive.Item value={EMPTY_SENTINEL} className={ITEM_CLASS}>
                  <SelectPrimitive.ItemText>
                    <span className="text-[var(--text-meta)]">{emptyLabel}</span>
                  </SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator className="ml-auto">
                    <Check size={14} aria-hidden />
                  </SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ) : null}
              {choices.map((choice) => (
                <SelectPrimitive.Item key={choice.id} value={choice.id} className={ITEM_CLASS}>
                  <SelectPrimitive.ItemText>{choice.name}</SelectPrimitive.ItemText>
                  <SelectPrimitive.ItemIndicator className="ml-auto">
                    <Check size={14} aria-hidden />
                  </SelectPrimitive.ItemIndicator>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </FormField>
  );
}
