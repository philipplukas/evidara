/**
 * `Combobox` — searchable single-select bound to `ra-core`'s `useInput`.
 *
 * The `<Select>` primitive renders every choice as a radix `<Select.Item>`,
 * which is right for a handful of options and wrong for a registry: the
 * jurisdiction picker fed 2,169 records into it, the caller capped the fetch at
 * 250 to keep it usable, and the result was a normal-looking dropdown that
 * silently ended at "Bovernier" — no Zürich, no federal jurisdictions, no hint
 * that anything was missing (#666).
 *
 * This primitive answers the same question differently: hold the full list,
 * search it, render a bounded window of matches, and *always* state what the
 * window covers via `describeComboboxStatus`. The status line is a live region
 * so screen-reader users get the same truncation warning sighted users get.
 *
 * Keyboard contract (WAI-ARIA combobox, manual selection):
 *   Down/Up      move the active option (opens the list when closed)
 *   Home/End     jump to first/last visible option
 *   Enter        commit the active option
 *   Escape       close and restore the committed value
 *   Tab          close, keeping the committed value
 */
"use client";

import { Check, ChevronDown } from "lucide-react";
import { useInput, useTranslate, type Validator } from "ra-core";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { cn } from "./cn";
import {
  type ComboboxChoice,
  describeComboboxStatus,
  filterComboboxChoices,
} from "./comboboxFilter";
import { FormField } from "./FormField";
import { translateValidationError } from "./validationError";

export type { ComboboxChoice } from "./comboboxFilter";

/**
 * How many options are rendered at once. Deliberately small: past ~50 rows the
 * operator is scrolling, not choosing, and the status line tells them to type
 * instead. Raising this does not change correctness — only how much scrolling
 * replaces typing.
 */
const MAX_VISIBLE_OPTIONS = 50;

interface ComboboxProps {
  source: string;
  label: string;
  choices: ComboboxChoice[];
  /**
   * Records the server reports as existing, when the caller knows it. Pass it
   * whenever the choice list came from a paginated fetch so a short fetch is
   * reported instead of silently presented as the whole registry.
   */
  totalCount?: number;
  description?: React.ReactNode;
  helperText?: React.ReactNode;
  disabled?: boolean;
  required?: boolean;
  validate?: Validator | Validator[];
  placeholder?: string;
  /** When true, offer an explicit "clear" option that resolves to `null`. */
  allowEmpty?: boolean;
  emptyLabel?: string;
  /** Shown instead of the option list while the caller is still fetching. */
  loading?: boolean;
  testId?: string;
}

const INPUT_CLASS =
  "w-full rounded-lg border bg-[var(--surface-input)] px-3 py-2.5 pr-9 text-sm " +
  "text-[var(--foreground)] placeholder:text-[var(--foreground-subtle)] " +
  "shadow-[var(--shadow-inset-surface)] transition-[border-color,box-shadow] " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const BORDER_OK = "border-[var(--border)] hover:border-[var(--accent-core)]/30";
const BORDER_ERROR = "border-[var(--status-critical)] hover:border-[var(--status-critical)]";

const LIST_CLASS =
  "absolute z-50 mt-1 w-full overflow-hidden rounded-lg border border-[var(--border)] " +
  "bg-[var(--surface-panel)] shadow-[var(--shadow-card)]";

const OPTION_CLASS =
  "flex w-full cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-2 " +
  "text-left text-sm text-[var(--foreground)] outline-none";

const OPTION_ACTIVE = "bg-[var(--interactive-accent-subtle)] text-[var(--accent-core)]" as const;

export function Combobox({
  source,
  label,
  choices,
  totalCount,
  description,
  helperText,
  disabled,
  required,
  validate,
  placeholder = "Type to search…",
  allowEmpty,
  emptyLabel = "None",
  loading,
  testId,
}: ComboboxProps) {
  const id = useId();
  const listboxId = `${id}-listbox`;
  const statusId = `${id}-status`;

  const translate = useTranslate();
  const { field, fieldState, isRequired } = useInput({ source, validate });
  const errorMessage =
    // Unwrap ra-core's "@@react-admin@@" validator envelope and translate it,
    // instead of showing the operator a raw i18n key (#671).
    translateValidationError(translate, fieldState.error?.message);
  const effectivelyRequired = required ?? isRequired;

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const selectedId = field.value == null || field.value === "" ? null : String(field.value);
  const selectedChoice = useMemo(
    () => choices.find((choice) => choice.id === selectedId) ?? null,
    [choices, selectedId],
  );

  const result = useMemo(
    () => filterComboboxChoices(choices, open ? query : "", MAX_VISIBLE_OPTIONS),
    [choices, open, query],
  );

  const status = describeComboboxStatus({
    query: open ? query : "",
    matchCount: result.matchCount,
    visibleCount: result.visible.length,
    loadedCount: result.loadedCount,
    totalCount,
  });

  /**
   * A committed value whose id is absent from the loaded choices is the exact
   * situation #666 produced silently. Say it out loud instead of rendering an
   * empty-looking field over a real stored value.
   */
  const selectionIsUnresolved = selectedId !== null && selectedChoice === null && !loading;

  const closeAndReset = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIndex(0);
  }, []);

  const commit = useCallback(
    (choiceId: string | null) => {
      field.onChange(choiceId);
      closeAndReset();
      inputRef.current?.focus();
    },
    [field, closeAndReset],
  );

  // Close on outside pointer-down so a click elsewhere in the form behaves the
  // way every other dropdown on the page does.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        closeAndReset();
        field.onBlur();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open, closeAndReset, field]);

  // Keep the active option inside the scroll viewport during keyboard nav.
  useEffect(() => {
    if (!open) return;
    const node = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    node?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex]);

  const optionCount = result.visible.length + (allowEmpty ? 1 : 0);
  // With `allowEmpty` the clear row occupies index 0 and choices shift by one.
  const emptyOffset = allowEmpty ? 1 : 0;

  const commitActive = () => {
    if (allowEmpty && activeIndex === 0) {
      commit(null);
      return;
    }
    const choice = result.visible[activeIndex - emptyOffset];
    if (choice) {
      commit(choice.id);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (!open) {
          setOpen(true);
          setActiveIndex(0);
          return;
        }
        setActiveIndex((current) => (optionCount === 0 ? 0 : (current + 1) % optionCount));
        return;
      case "ArrowUp":
        event.preventDefault();
        if (!open) {
          setOpen(true);
          setActiveIndex(Math.max(optionCount - 1, 0));
          return;
        }
        setActiveIndex((current) =>
          optionCount === 0 ? 0 : (current - 1 + optionCount) % optionCount,
        );
        return;
      case "Home":
        if (!open) return;
        event.preventDefault();
        setActiveIndex(0);
        return;
      case "End":
        if (!open) return;
        event.preventDefault();
        setActiveIndex(Math.max(optionCount - 1, 0));
        return;
      case "Enter":
        if (!open) return;
        event.preventDefault();
        commitActive();
        return;
      case "Escape":
        if (!open) return;
        event.preventDefault();
        closeAndReset();
        return;
      case "Tab":
        if (open) closeAndReset();
        return;
      default:
    }
  };

  const displayValue = open ? query : (selectedChoice?.name ?? "");

  return (
    <FormField
      id={id}
      label={label}
      required={effectivelyRequired}
      description={description}
      helperText={helperText}
      error={errorMessage}
    >
      <div className="relative" ref={rootRef} data-testid={testId}>
        <input
          id={id}
          ref={(node) => {
            inputRef.current = node;
            field.ref(node);
          }}
          type="text"
          role="combobox"
          autoComplete="off"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-describedby={statusId}
          aria-activedescendant={
            open && optionCount > 0 ? `${id}-option-${activeIndex}` : undefined
          }
          aria-invalid={!!errorMessage}
          aria-required={effectivelyRequired || undefined}
          disabled={disabled}
          value={displayValue}
          placeholder={selectedChoice ? selectedChoice.name : placeholder}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          className={cn(INPUT_CLASS, errorMessage ? BORDER_ERROR : BORDER_OK)}
        />
        <ChevronDown
          size={16}
          aria-hidden
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--foreground-subtle)]"
        />

        {/*
         * Always rendered (not only when open) and always a live region, so the
         * coverage sentence is available to assistive tech at the moment the
         * option list changes under it.
         */}
        <p id={statusId} aria-live="polite" className="mt-1 text-[12px] text-[var(--text-meta)]">
          {loading ? "Loading options…" : status}
        </p>

        {selectionIsUnresolved ? (
          <p className="mt-1 text-[12px] font-medium text-[var(--status-degraded)]">
            Saved value <span className="font-mono">{selectedId}</span> is not in the loaded options
            — it may exist outside the fetched window.
          </p>
        ) : null}

        {/*
         * `<div role="listbox">` / `<div role="option">` rather than `<ul>/<li>`:
         * the ARIA combobox pattern keeps DOM focus in the text input and moves
         * a *virtual* cursor via `aria-activedescendant`, so options carry
         * `tabIndex={-1}` (programmatically focusable, never in the tab order).
         * `<li role="option">` trips Biome's non-interactive-element rules for
         * exactly that reason.
         */}
        {open ? (
          <div
            id={listboxId}
            ref={listRef}
            role="listbox"
            aria-label={label}
            className={cn(LIST_CLASS, "max-h-[320px] overflow-y-auto p-1.5")}
          >
            {allowEmpty ? (
              <div
                id={`${id}-option-0`}
                data-index={0}
                role="option"
                tabIndex={-1}
                aria-selected={selectedId === null}
                onPointerDown={(event) => {
                  event.preventDefault();
                  commit(null);
                }}
                onMouseEnter={() => setActiveIndex(0)}
                className={cn(OPTION_CLASS, activeIndex === 0 ? OPTION_ACTIVE : undefined)}
              >
                <span className="text-[var(--text-meta)]">{emptyLabel}</span>
                {selectedId === null ? <Check size={14} aria-hidden className="ml-auto" /> : null}
              </div>
            ) : null}

            {result.visible.map((choice, index) => {
              const optionIndex = index + emptyOffset;
              const isSelected = choice.id === selectedId;
              return (
                <div
                  key={choice.id}
                  id={`${id}-option-${optionIndex}`}
                  data-index={optionIndex}
                  role="option"
                  tabIndex={-1}
                  aria-selected={isSelected}
                  onPointerDown={(event) => {
                    event.preventDefault();
                    commit(choice.id);
                  }}
                  onMouseEnter={() => setActiveIndex(optionIndex)}
                  className={cn(
                    OPTION_CLASS,
                    activeIndex === optionIndex ? OPTION_ACTIVE : undefined,
                    isSelected ? "font-semibold text-[var(--accent-core)]" : undefined,
                  )}
                >
                  <span className="truncate">{choice.name}</span>
                  {isSelected ? <Check size={14} aria-hidden className="ml-auto" /> : null}
                </div>
              );
            })}

            {optionCount === 0 ? (
              <p className="px-2.5 py-2 text-sm text-[var(--text-meta)]">
                {loading ? "Loading options…" : "No matching options"}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </FormField>
  );
}
