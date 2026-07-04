/**
 * `Checkbox` — controlled boolean input built on a native `<input
 * type="checkbox">` styled with design tokens. Zero MUI, zero new deps.
 *
 * Unlike `TextInput` / `Select` (which bind to `ra-core`'s `useInput`), this
 * primitive is fully controlled via `checked` / `onCheckedChange` so it can
 * back local `useState` dialog forms — the source-version editor on
 * `SourceShow` manages its form state locally rather than through a
 * `<Form>` context.
 */
"use client";

import { Check } from "lucide-react";
import { useId } from "react";
import { cn } from "./cn";

interface CheckboxProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  className?: string;
}

export function Checkbox({
  checked,
  onCheckedChange,
  label,
  description,
  disabled,
  className,
}: CheckboxProps) {
  const id = useId();

  return (
    <div className={cn("flex items-start gap-2.5", className)}>
      <span className="relative inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onCheckedChange(event.target.checked)}
          className={cn(
            "peer h-[18px] w-[18px] cursor-pointer appearance-none rounded-[5px] border",
            "border-[var(--border)] bg-[var(--surface-input)] shadow-[var(--shadow-inset-surface)]",
            "transition-colors checked:border-[var(--accent-core)] checked:bg-[var(--accent-core)]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        />
        <Check
          size={12}
          strokeWidth={3}
          aria-hidden
          className="pointer-events-none absolute text-[var(--accent-core-foreground)] opacity-0 peer-checked:opacity-100"
        />
      </span>
      <label
        htmlFor={id}
        className={cn(
          "select-none text-[13px] leading-[1.35] text-[var(--foreground)]",
          disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
        )}
      >
        <span className="font-medium">{label}</span>
        {description ? (
          <span className="block text-[12px] text-[var(--foreground-subtle)]">{description}</span>
        ) : null}
      </label>
    </div>
  );
}
