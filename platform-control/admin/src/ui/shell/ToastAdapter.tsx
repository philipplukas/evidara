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
import { useNotificationContext } from "ra-core";
import { useEffect, useState } from "react";
import { Toast } from "./Toast";

export type NotificationType = "success" | "info" | "warning" | "error";

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
  const [active, setActive] = useState<ActiveNotification[]>([]);

  useEffect(() => {
    if (notifications.length === 0) return;
    const next = takeNotification();
    if (!next) return;
    setActive((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: toNotificationType(next.type),
        message: next.message,
        duration: next.notificationOptions?.autoHideDuration ?? 5000,
        open: true,
      },
    ]);
  }, [notifications, takeNotification]);

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
