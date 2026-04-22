"use client";

import { useCallback, useSyncExternalStore } from "react";

// ─── Types ───

export type ToastVariant = "success" | "error" | "info";

export interface Toast {
  id: string;
  variant: ToastVariant;
  title: string;
  description?: string;
  /** Auto-dismiss delay in ms. `0` means persist until dismissed. Default: 3500. */
  duration?: number;
}

export type ToastInput = Omit<Toast, "id">;

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

// ─── Imperative API (for use outside React) ───

export const toast = {
  success: (title: string, description?: string) =>
    addToast({ variant: "success", title, description }),
  error: (title: string, description?: string) =>
    addToast({ variant: "error", title, description }),
  info: (title: string, description?: string) => addToast({ variant: "info", title, description }),
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
        (title: string, description?: string) =>
          addToast({ variant: "success", title, description }),
        [],
      ),
      error: useCallback(
        (title: string, description?: string) => addToast({ variant: "error", title, description }),
        [],
      ),
      info: useCallback(
        (title: string, description?: string) => addToast({ variant: "info", title, description }),
        [],
      ),
      custom: useCallback((input: ToastInput) => addToast(input), []),
      dismiss: useCallback((id: string) => dismissToast(id), []),
    },
  };
}
