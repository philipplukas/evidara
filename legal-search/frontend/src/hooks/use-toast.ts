"use client";

import { useCallback, useSyncExternalStore } from "react";

// ─── Types ───

export type ToastVariant = "success" | "error" | "info";

/** Optional action affordance rendered inside a toast (e.g. "Undo"). */
export interface ToastAction {
  label: string;
  onClick: () => void;
  /** Required by Radix for screen readers when an action is present. Defaults to `label`. */
  altText?: string;
}

export interface Toast {
  id: string;
  variant: ToastVariant;
  title: string;
  description?: string;
  /** Auto-dismiss delay in ms. `0` means persist until dismissed. Default: 3500. */
  duration?: number;
  action?: ToastAction;
}

export type ToastInput = Omit<Toast, "id">;

/** Optional opts for the fire-and-forget helpers. */
export interface ToastOptions {
  description?: string;
  duration?: number;
  action?: ToastAction;
}

// ─── Store (module-singleton, framework-agnostic) ───

let toasts: Toast[] = [];
let nextId = 0;
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function getSnapshot(): Toast[] {
  return toasts;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Add a toast and return its id. */
function addToast(input: ToastInput): string {
  const id = `toast-${++nextId}`;
  const duration = input.duration ?? 3500;
  toasts = [...toasts, { ...input, id, duration }];
  emit();

  if (duration > 0) {
    setTimeout(() => dismissToast(id), duration);
  }
  return id;
}

/** Remove a toast by id. */
function dismissToast(id: string): void {
  const prev = toasts;
  toasts = toasts.filter((t) => t.id !== id);
  if (toasts !== prev) emit();
}

/**
 * Normalize the second argument of `toast.success`/`.error`/`.info`.
 *
 * Supports both the legacy string form (`toast.info("title", "description")`)
 * and the extended options form (`toast.info("title", { action: … })`).
 */
function normalizeOpts(opts?: string | ToastOptions): ToastOptions {
  if (typeof opts === "string") return { description: opts };
  return opts ?? {};
}

// ─── Imperative API (for use outside React) ───

export const toast = {
  success: (title: string, opts?: string | ToastOptions) =>
    addToast({ variant: "success", title, ...normalizeOpts(opts) }),
  error: (title: string, opts?: string | ToastOptions) =>
    addToast({ variant: "error", title, ...normalizeOpts(opts) }),
  info: (title: string, opts?: string | ToastOptions) =>
    addToast({ variant: "info", title, ...normalizeOpts(opts) }),
  custom: (input: ToastInput) => addToast(input),
  dismiss: dismissToast,
};

// ─── React hook ───

export function useToast() {
  const current = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  return {
    toasts: current,
    toast: {
      success: useCallback(
        (title: string, opts?: string | ToastOptions) =>
          addToast({ variant: "success", title, ...normalizeOpts(opts) }),
        [],
      ),
      error: useCallback(
        (title: string, opts?: string | ToastOptions) =>
          addToast({ variant: "error", title, ...normalizeOpts(opts) }),
        [],
      ),
      info: useCallback(
        (title: string, opts?: string | ToastOptions) =>
          addToast({ variant: "info", title, ...normalizeOpts(opts) }),
        [],
      ),
      custom: useCallback((input: ToastInput) => addToast(input), []),
      dismiss: useCallback((id: string) => dismissToast(id), []),
    },
  };
}
