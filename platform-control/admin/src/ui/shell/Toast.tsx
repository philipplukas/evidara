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
    "bg-[#f0fdf4] text-[#166534] border-[rgba(22,101,52,0.35)] [&_.toast-accent]:bg-[#166534]",
  info: "bg-[#eff6ff] text-[#1e40af] border-[rgba(30,64,175,0.35)] [&_.toast-accent]:bg-[#1e40af]",
  warning:
    "bg-[#fffbeb] text-[#92400e] border-[rgba(146,64,14,0.4)] [&_.toast-accent]:bg-[#92400e]",
  error: "bg-[#fef2f2] text-[#991b1b] border-[rgba(153,27,27,0.4)] [&_.toast-accent]:bg-[#991b1b]",
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
      className={`pointer-events-auto relative flex items-start gap-3 min-w-[280px] max-w-[420px] pl-4 pr-10 py-3 rounded-2xl border shadow-[var(--shadow-panel)] backdrop-blur-[10px] motion-safe:animate-[evidara-toast-in_180ms_cubic-bezier(0.4,0,0.2,1)] data-[state=closed]:motion-safe:animate-[evidara-toast-out_140ms_cubic-bezier(0.4,0,0.2,1)] ${LEVEL_CLASS[type]}`}
    >
      <span aria-hidden className="toast-accent absolute left-0 top-0 bottom-0 w-1 rounded-l-2xl" />
      <ToastPrimitive.Description asChild>
        <div className="min-w-0 flex-1 text-[13px] leading-snug font-medium">{message}</div>
      </ToastPrimitive.Description>
      <ToastPrimitive.Close
        aria-label="Dismiss notification"
        className="absolute right-2 top-2 inline-flex items-center justify-center w-7 h-7 rounded-full text-current/70 hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--brand-focus-ring)]"
      >
        <CloseIcon size={14} strokeWidth={2.2} aria-hidden />
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  );
}
