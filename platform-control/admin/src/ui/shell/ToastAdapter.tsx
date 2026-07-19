/**
 * `ToastAdapter` — subscribes to `ra-core`'s `NotificationContext` and
 * renders a stack of `<Toast>` bubbles bottom-right via
 * `@radix-ui/react-toast` primitives.
 *
 * Any `useNotify()` call in any page (v1 MUI or v2 Tailwind) now lands
 * here instead of MUI's `<Notification>` Snackbar. v1 pages that
 * previously threw up a MUI toast keep working unchanged — only the
 * rendering layer flipped.
 *
 * Mount once at the shell root. `ToastPrimitive.Provider` wires the
 * keyboard shortcut (F8) and swipe direction; `ToastPrimitive.Viewport`
 * portals the stack out of the grid so z-index stays simple.
 */
"use client";

import * as ToastPrimitive from "@radix-ui/react-toast";
import { useNotificationContext, useTranslate } from "ra-core";
import { useCallback, useEffect, useState } from "react";
import { Toast } from "./Toast";

export type NotificationType = "success" | "info" | "warning" | "error";

/**
 * `ra-core` publishes the **i18n key** as `notification.message` and expects the
 * renderer to translate it — the MUI `<Notification>` this adapter replaced did
 * that internally (ADR-0026 P4a). Rendering `message` raw is why operators saw
 * `ra.notification.item_doesnt_exist` and `ra.message.invalid_form` as toast
 * titles (#671).
 *
 * Exported for unit testing: takes a `translate` fn plus the raw message and
 * returns what should be displayed. App-authored literals ("Could not create
 * source: …") are passed through untouched, because `translate` is called with
 * a `_` default equal to the input — the catalogue only wins when it has an
 * entry.
 */
export function translateNotificationMessage(
  translate: (key: string, options: { _: string }) => string,
  message: React.ReactNode,
): React.ReactNode {
  if (typeof message !== "string") {
    return message;
  }
  try {
    return translate(message, { _: message });
  } catch {
    // A missing catalogue must never cost the operator the message itself.
    return message;
  }
}

interface ActiveNotification {
  id: string;
  type: NotificationType;
  message: React.ReactNode;
  duration: number | null;
  open: boolean;
}

function toNotificationType(raw: unknown): NotificationType {
  if (raw === "success" || raw === "info" || raw === "warning" || raw === "error") {
    return raw;
  }
  return "info";
}

export function ToastAdapter() {
  const { notifications, takeNotification } = useNotificationContext();
  const rawTranslate = useTranslate();
  const [active, setActive] = useState<ActiveNotification[]>([]);

  const translate = useCallback(
    (key: string, options: { _: string }) => rawTranslate(key, options),
    [rawTranslate],
  );

  useEffect(() => {
    if (notifications.length === 0) return;
    const next = takeNotification();
    if (!next) return;
    setActive((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: toNotificationType(next.type),
        message: translateNotificationMessage(translate, next.message),
        duration: next.notificationOptions?.autoHideDuration ?? 5000,
        open: true,
      },
    ]);
  }, [notifications, takeNotification, translate]);

  // Drop closed toasts after their exit animation completes. Radix owns the
  // open→closed transition; we wait a frame past `open=false` before GCing
  // so the data-[state=closed] exit animation has time to play.
  useEffect(() => {
    const hasClosed = active.some((n) => !n.open);
    if (!hasClosed) return;
    const timer = window.setTimeout(() => {
      setActive((prev) => prev.filter((n) => n.open));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [active]);

  return (
    <ToastPrimitive.Provider label="Notifications" swipeDirection="right" duration={5000}>
      {active.map((n) => (
        <Toast
          key={n.id}
          type={n.type}
          message={n.message}
          duration={n.duration}
          open={n.open}
          onOpenChange={(open) => {
            setActive((prev) => prev.map((p) => (p.id === n.id ? { ...p, open } : p)));
          }}
        />
      ))}
      <ToastPrimitive.Viewport
        aria-label="Notifications"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end list-none m-0 p-0 outline-none"
      />
    </ToastPrimitive.Provider>
  );
}
