"use client";

import type * as React from "react";
import { type ReactNode } from "react";
import { Button, type ConsequenceTier } from "@/components/ui/button";

/**
 * @deprecated Prefer `<Button tier="notable" | "destructive" … />` from `@/components/ui/button` (ADR-0016 Contract 8).
 * This wrapper remains for call sites that use the `onConfirm` prop name.
 */
export type ConfirmButtonProps = Omit<React.ComponentProps<typeof Button>, "onClick"> & {
  onConfirm: () => void | Promise<void>;
  children: ReactNode;
};

export type { ConsequenceTier };

export function ConfirmButton({
  tier = "safe",
  confirmTitle,
  confirmDescription,
  confirmLabel,
  cancelLabel,
  onConfirm,
  children,
  ...buttonProps
}: ConfirmButtonProps) {
  return (
    <Button
      tier={tier}
      confirmTitle={confirmTitle}
      confirmDescription={confirmDescription}
      confirmLabel={confirmLabel}
      cancelLabel={cancelLabel}
      onClick={() => void onConfirm()}
      {...buttonProps}
    >
      {children}
    </Button>
  );
}
