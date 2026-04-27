/**
 * `Button` — Tailwind-based button primitive, zero MUI.
 *
 * Variants (primary/secondary/ghost) map to the semantic roles the admin
 * needs today: primary CTAs, secondary surfaces, ghost inline actions.
 * Sizes (sm/md) include the 44px mobile tap-target floor from UX-8.
 */
"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-lg font-semibold " +
  "transition-[background-color,border-color,transform,box-shadow] duration-150 " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-[var(--accent-core)] text-[var(--accent-core-foreground)] border border-transparent shadow-[var(--shadow-card)] " +
    "hover:bg-[color-mix(in_oklab,var(--accent-core)_88%,black)] hover:shadow-[var(--shadow-card-hover)]",
  secondary:
    "bg-[var(--surface-panel)] text-[var(--foreground)] border border-[var(--border)] shadow-[var(--shadow-ring-subtle)] " +
    "hover:bg-[var(--surface-input)] hover:border-[var(--accent-core)]/30",
  ghost:
    "bg-transparent text-[var(--accent-core)] border border-transparent " +
    "hover:bg-[var(--interactive-accent-subtle)]",
};

const SIZE: Record<Size, string> = {
  sm: "px-3 h-8 text-xs",
  md: "px-4 min-h-11 sm:h-10 text-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  leftIcon,
  rightIcon,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button type={type} className={cn(BASE, VARIANT[variant], SIZE[size], className)} {...rest}>
      {leftIcon ? <span aria-hidden>{leftIcon}</span> : null}
      {children}
      {rightIcon ? <span aria-hidden>{rightIcon}</span> : null}
    </button>
  );
}
