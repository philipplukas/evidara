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
  "inline-flex items-center justify-center gap-2 rounded-full font-semibold " +
  "transition-[background-color,border-color,transform,box-shadow] duration-150 " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-[rgba(15,76,129,0.42)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-[#0f4c81] text-[#fffdf8] border border-transparent shadow-[0_10px_24px_rgba(15,76,129,0.18)] " +
    "hover:bg-[#0b3d68] hover:shadow-[0_14px_28px_rgba(15,76,129,0.24)]",
  secondary:
    "bg-white/80 text-[#1d293d] border border-[rgba(29,41,61,0.12)] " +
    "hover:bg-white hover:border-[rgba(29,41,61,0.2)]",
  ghost:
    "bg-transparent text-[#0f4c81] border border-transparent " + "hover:bg-[rgba(15,76,129,0.08)]",
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
