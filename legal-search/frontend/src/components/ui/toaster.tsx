"use client";

import {
  ToastAction,
  ToastClose,
  ToastDescription,
  ToastIcon,
  ToastProvider,
  ToastRoot,
  ToastTitle,
  ToastViewport,
} from "@/components/ui/toast";
import { useToast } from "@/hooks/use-toast";

/**
 * Renders all active toasts. Mount once in the app (e.g. inside Providers).
 */
export function Toaster() {
  const { toasts } = useToast();

  return (
    <ToastProvider>
      {toasts.map((t) => (
        <ToastRoot key={t.id} variant={t.variant} duration={t.duration}>
          <ToastIcon variant={t.variant} />
          <div className="flex flex-1 flex-col gap-0.5">
            <ToastTitle>{t.title}</ToastTitle>
            {t.description && <ToastDescription>{t.description}</ToastDescription>}
          </div>
          {t.action && (
            <ToastAction altText={t.action.altText ?? t.action.label} onClick={t.action.onClick}>
              {t.action.label}
            </ToastAction>
          )}
          <ToastClose />
        </ToastRoot>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}
