/**
 * `Toast` — single visible notification surface, built on `@radix-ui/react-toast`.
 *
 * Colour mapping matches `Pill` levels (info / success → healthy / warning →
 * degraded / error → critical) so severity reads consistently with the rest
 * of the admin's status surfaces (UX-4 pill contract).
 *
 * `<ToastPrimitive.Root>` handles auto-dismiss, pause-on-hover,
 * pause-on-focus, keyboard shortcut (F8 → focus viewport), and swipe-to-
 * dismiss. `prefers-reduced-motion` short-circuits our CSS animation via
 * `motion-safe:`.
 *
 * This component is the single-toast surface; the viewport (stack + portal)
 * and provider live in `ToastAdapter`.
 */
"use client";

import * as ToastPrimitive from "@radix-ui/react-toast";
import { X as CloseIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { NotificationType } from "./ToastAdapter";

const LEVEL_CLASS: Record<NotificationType, string> = {
  success:
    "bg-[var(--status-healthy-subtle)] text-[var(--status-healthy)] border-[var(--status-healthy)]/25 [&_.toast-accent]:bg-[var(--status-healthy)]",
  info: "bg-[var(--status-info-subtle)] text-[var(--status-info)] border-[var(--status-info)]/25 [&_.toast-accent]:bg-[var(--status-info)]",
  warning:
    "bg-[var(--status-degraded-subtle)] text-[var(--status-degraded)] border-[var(--status-degraded)]/30 [&_.toast-accent]:bg-[var(--status-degraded)]",
  error:
    "bg-[var(--status-critical-subtle)] text-[var(--status-critical)] border-[var(--status-critical)]/30 [&_.toast-accent]:bg-[var(--status-critical)]",
};

interface ToastProps {
  type: NotificationType;
  message: ReactNode;
  /** ms before auto-dismiss. `null` disables auto-close. Default 5000. */
  duration?: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function Toast({ type, message, duration = 5000, open, onOpenChange }: ToastProps) {
  return (
    <ToastPrimitive.Root
      open={open}
      onOpenChange={onOpenChange}
      duration={duration == null ? Number.POSITIVE_INFINITY : duration}
      type={type === "error" ? "foreground" : "background"}
      className={`pointer-events-auto relative flex min-w-[280px] max-w-[420px] items-start gap-3 rounded-lg border py-3 pl-4 pr-10 shadow-[var(--shadow-panel)] motion-safe:animate-[evidara-toast-in_180ms_cubic-bezier(0.4,0,0.2,1)] data-[state=closed]:motion-safe:animate-[evidara-toast-out_140ms_cubic-bezier(0.4,0,0.2,1)] ${LEVEL_CLASS[type]}`}
    >
      <span aria-hidden className="toast-accent absolute bottom-0 left-0 top-0 w-1 rounded-l-lg" />
      <ToastPrimitive.Description asChild>
        <div className="min-w-0 flex-1 text-[13px] leading-snug font-medium">{message}</div>
      </ToastPrimitive.Description>
      <ToastPrimitive.Close
        aria-label="Dismiss notification"
        className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-lg text-current/70 hover:bg-[var(--interactive-accent-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
      >
        <CloseIcon size={14} strokeWidth={2.2} aria-hidden />
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  );
}
