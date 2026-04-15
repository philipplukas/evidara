"use client";

import { type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { type ReactNode, useState } from "react";
import { Button, buttonVariants } from "./button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "./popover";

export type ConsequenceTier = "safe" | "notable" | "destructive";

interface ConfirmButtonProps
  extends React.ComponentProps<"button">,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  tier?: ConsequenceTier;
  confirmTitle?: string;
  confirmDescription?: string;
  confirmLabel?: string;
  cancelLabel?: string;
}

export function ConfirmButton({
  tier = "safe",
  confirmTitle,
  confirmDescription,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onClick,
  children,
  ...buttonProps
}: ConfirmButtonProps) {
  if (tier === "safe") {
    return (
      <Button {...buttonProps} onClick={onClick}>
        {children}
      </Button>
    );
  }

  if (tier === "notable") {
    return (
      <NotableConfirm
        cancelLabel={cancelLabel}
        confirmDescription={confirmDescription}
        confirmLabel={confirmLabel}
        confirmTitle={confirmTitle ?? "Are you sure?"}
        onConfirm={onClick}
        buttonProps={buttonProps}
      >
        {children}
      </NotableConfirm>
    );
  }

  return (
    <DestructiveConfirm
      cancelLabel={cancelLabel}
      confirmDescription={confirmDescription}
      confirmLabel={confirmLabel}
      confirmTitle={confirmTitle ?? "This action cannot be undone"}
      onConfirm={onClick}
      buttonProps={buttonProps}
    >
      {children}
    </DestructiveConfirm>
  );
}

function NotableConfirm({
  buttonProps,
  cancelLabel,
  children,
  confirmDescription,
  confirmLabel,
  confirmTitle,
  onConfirm,
}: {
  buttonProps: Omit<
    ConfirmButtonProps,
    | "tier"
    | "onClick"
    | "children"
    | "confirmTitle"
    | "confirmDescription"
    | "confirmLabel"
    | "cancelLabel"
  >;
  cancelLabel: string;
  children: ReactNode;
  confirmDescription?: string;
  confirmLabel: string;
  confirmTitle: string;
  onConfirm: React.MouseEventHandler<HTMLButtonElement> | undefined;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger asChild>
        <Button {...buttonProps} type="button">
          {children}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        <PopoverHeader>
          <PopoverTitle>{confirmTitle}</PopoverTitle>
          {confirmDescription ? (
            <PopoverDescription>{confirmDescription}</PopoverDescription>
          ) : null}
        </PopoverHeader>
        <div className="flex justify-end gap-2">
          <Button size="sm" type="button" variant="ghost" onClick={() => setOpen(false)}>
            {cancelLabel}
          </Button>
          <Button
            size="sm"
            type="button"
            variant="default"
            onClick={(e) => {
              setOpen(false);
              onConfirm?.(e);
            }}
          >
            {confirmLabel}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function DestructiveConfirm({
  buttonProps,
  cancelLabel,
  children,
  confirmDescription,
  confirmLabel,
  confirmTitle,
  onConfirm,
}: {
  buttonProps: Omit<
    ConfirmButtonProps,
    | "tier"
    | "onClick"
    | "children"
    | "confirmTitle"
    | "confirmDescription"
    | "confirmLabel"
    | "cancelLabel"
  >;
  cancelLabel: string;
  children: ReactNode;
  confirmDescription?: string;
  confirmLabel: string;
  confirmTitle: string;
  onConfirm: React.MouseEventHandler<HTMLButtonElement> | undefined;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button {...buttonProps} type="button" onClick={() => setOpen(true)}>
        {children}
      </Button>
      <Dialog onOpenChange={setOpen} open={open}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmTitle}</DialogTitle>
            {confirmDescription ? (
              <DialogDescription>{confirmDescription}</DialogDescription>
            ) : null}
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              {cancelLabel}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={(e) => {
                setOpen(false);
                onConfirm?.(e);
              }}
            >
              {confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
