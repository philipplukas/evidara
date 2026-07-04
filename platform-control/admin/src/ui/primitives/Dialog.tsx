/**
 * `Dialog` — self-contained modal primitive, zero MUI and zero new runtime
 * deps. It portals its content to `document.body`, dims the page with a
 * backdrop, closes on Escape / backdrop click (unless `dismissable` is
 * false, e.g. while a submit is in flight), and traps Tab focus within the
 * panel so keyboard users can't escape into the page behind it.
 *
 * The admin uses `@radix-ui/react-select` for the token-styled dropdowns, but
 * `@radix-ui/react-dialog` is intentionally not a dependency (see ADR-0026 —
 * we keep the primitive surface small and dependency-light). This hand-rolled
 * dialog covers the source-version editor + confirm flows on `SourceShow`
 * without pulling a new package into the lockfile.
 */
"use client";

import { X } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { cn } from "./cn";

type DialogSize = "sm" | "md";

const SIZE: Record<DialogSize, string> = {
  sm: "max-w-md",
  md: "max-w-2xl",
};

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: DialogSize;
  /**
   * When false, Escape, backdrop click, and the close button are all
   * disabled — used to keep the dialog open while a mutation is in flight.
   */
  dismissable?: boolean;
  testId?: string;
}

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  dismissable = true,
  testId,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  const requestClose = useCallback(() => {
    if (dismissable) {
      onClose();
    }
  }, [dismissable, onClose]);

  // Escape-to-close + Tab focus trap. Registered only while open so we don't
  // leave a dangling listener on the document.
  useEffect(() => {
    if (!open) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        requestClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const panel = panelRef.current;
      if (!panel) {
        return;
      }
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (element) => element.offsetParent !== null || element === document.activeElement,
      );
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [open, requestClose]);

  // Move focus into the panel on open and lock body scroll while it's up.
  useEffect(() => {
    if (!open) {
      return;
    }
    const previousActive = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Focus the first focusable control, falling back to the panel itself.
    const panel = panelRef.current;
    const firstFocusable = panel?.querySelector<HTMLElement>(FOCUSABLE);
    (firstFocusable ?? panel)?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousActive?.focus?.();
    };
  }, [open]);

  if (!open || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto p-4 sm:p-6"
      data-testid={testId}
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close dialog"
        tabIndex={-1}
        onClick={requestClose}
        className="fixed inset-0 bg-[color-mix(in_oklab,var(--foreground)_45%,transparent)] backdrop-blur-[2px]"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          "relative z-[101] my-auto w-full rounded-[16px] border border-[var(--border)]",
          "bg-[var(--admin-panel-bg)] shadow-[var(--shadow-card-hover)] backdrop-blur-[12px]",
          "focus:outline-none",
          SIZE[size],
        )}
      >
        <div className="flex items-start justify-between gap-4 px-5 pt-5 sm:px-6 sm:pt-6">
          <div className="space-y-1">
            <h2 id={titleId} className="text-[16px] font-semibold text-[var(--foreground)]">
              {title}
            </h2>
            {description ? (
              <p id={descriptionId} className="text-[13px] text-[var(--foreground-subtle)]">
                {description}
              </p>
            ) : null}
          </div>
          {dismissable ? (
            <button
              type="button"
              onClick={requestClose}
              aria-label="Close"
              className="shrink-0 rounded-md p-1 text-[var(--foreground-subtle)] hover:bg-[var(--brand-wash-4)] hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
            >
              <X size={16} aria-hidden />
            </button>
          ) : null}
        </div>

        <div className="px-5 py-4 sm:px-6">{children}</div>

        {footer ? (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[var(--border-faint)] px-5 py-4 sm:px-6">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
