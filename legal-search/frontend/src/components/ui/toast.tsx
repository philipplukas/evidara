"use client";

import { CheckCircle2Icon, InfoIcon, XCircleIcon, XIcon } from "lucide-react";
import { Toast as ToastPrimitive } from "radix-ui";
import type * as React from "react";
import { cn } from "@/lib/utils";

// ─── Variant helpers ───

const variantStyles = {
  success:
    "border-[var(--status-healthy)]/20 bg-[var(--status-healthy-subtle)] text-[var(--status-healthy)]",
  error:
    "border-destructive/20 bg-[var(--status-critical-subtle)] text-[var(--status-critical)]",
  info: "border-[var(--status-info)]/20 bg-[var(--status-info-subtle)] text-[var(--status-info)]",
} as const;

const variantIcons = {
  success: CheckCircle2Icon,
  error: XCircleIcon,
  info: InfoIcon,
} as const;

export type ToastVariant = keyof typeof variantStyles;

// ─── Provider / Viewport ───

function ToastProvider({ ...props }: React.ComponentProps<typeof ToastPrimitive.Provider>) {
  return <ToastPrimitive.Provider data-slot="toast-provider" swipeDirection="right" {...props} />;
}

function ToastViewport({
  className,
  ...props
}: React.ComponentProps<typeof ToastPrimitive.Viewport>) {
  return (
    <ToastPrimitive.Viewport
      data-slot="toast-viewport"
      className={cn(
        "fixed bottom-4 right-4 z-[var(--z-toast)] flex max-h-screen w-full max-w-sm flex-col-reverse gap-2 outline-none",
        className,
      )}
      {...props}
    />
  );
}

// ─── Toast root ───

function ToastRoot({
  className,
  variant = "info",
  ...props
}: React.ComponentProps<typeof ToastPrimitive.Root> & { variant?: ToastVariant }) {
  return (
    <ToastPrimitive.Root
      data-slot="toast"
      className={cn(
        "group pointer-events-auto flex w-full items-start gap-3 rounded-xl border p-4 shadow-lg transition-all",
        "data-[state=open]:animate-in data-[state=open]:slide-in-from-right-full data-[state=open]:fade-in-0",
        "data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right-full data-[state=closed]:fade-out-0",
        "data-[swipe=move]:translate-x-[var(--radix-toast-swipe-move-x)]",
        "data-[swipe=cancel]:translate-x-0 data-[swipe=cancel]:transition-transform",
        "data-[swipe=end]:animate-out data-[swipe=end]:slide-out-to-right-full",
        variantStyles[variant],
        className,
      )}
      {...props}
    />
  );
}

// ─── Toast parts ───

function ToastIcon({ variant }: { variant: ToastVariant }) {
  const Icon = variantIcons[variant];
  return <Icon data-slot="toast-icon" className="mt-0.5 h-4 w-4 shrink-0" />;
}

function ToastTitle({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Title>) {
  return (
    <ToastPrimitive.Title
      data-slot="toast-title"
      className={cn("text-sm font-medium leading-snug text-foreground", className)}
      {...props}
    />
  );
}

function ToastDescription({
  className,
  ...props
}: React.ComponentProps<typeof ToastPrimitive.Description>) {
  return (
    <ToastPrimitive.Description
      data-slot="toast-description"
      className={cn("text-xs leading-normal text-muted-foreground", className)}
      {...props}
    />
  );
}

function ToastClose({ className, ...props }: React.ComponentProps<typeof ToastPrimitive.Close>) {
  return (
    <ToastPrimitive.Close
      data-slot="toast-close"
      className={cn(
        "ml-auto inline-flex shrink-0 items-center justify-center rounded-md p-1 text-muted-foreground/60 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
        className,
      )}
      aria-label="Close"
      {...props}
    >
      <XIcon className="h-3.5 w-3.5" />
    </ToastPrimitive.Close>
  );
}

export {
  ToastClose,
  ToastDescription,
  ToastIcon,
  ToastProvider,
  ToastRoot,
  ToastTitle,
  ToastViewport,
};
