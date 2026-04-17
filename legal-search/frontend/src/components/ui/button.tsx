"use client";

import { Slot } from "radix-ui";
import type * as React from "react";
import { type MouseEvent, type ReactNode, useState } from "react";
import { buttonVariants, type VariantProps } from "@/components/ui/button-variants";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export type ConsequenceTier = "safe" | "notable" | "destructive";

type ButtonBaseProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  };

function ButtonBase({ className, variant = "default", size = "default", asChild = false, ...props }: ButtonBaseProps) {
  const Comp = asChild ? Slot.Root : "button";

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

type ButtonProps = ButtonBaseProps & {
  tier?: ConsequenceTier;
  confirmTitle?: string;
  confirmDescription?: string;
  confirmLabel?: string;
  cancelLabel?: string;
};

function Button({
  tier = "safe",
  confirmTitle,
  confirmDescription,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onClick,
  children,
  ...buttonProps
}: ButtonProps) {
  if (tier === "safe") {
    return (
      <ButtonBase {...buttonProps} onClick={onClick}>
        {children}
      </ButtonBase>
    );
  }

  if (tier === "notable") {
    return (
      <NotableConfirm
        buttonProps={buttonProps}
        cancelLabel={cancelLabel}
        confirmDescription={confirmDescription}
        confirmLabel={confirmLabel}
        confirmTitle={confirmTitle ?? "Are you sure?"}
        onConfirm={onClick}
      >
        {children}
      </NotableConfirm>
    );
  }

  return (
    <DestructiveConfirm
      buttonProps={buttonProps}
      cancelLabel={cancelLabel}
      confirmDescription={confirmDescription}
      confirmLabel={confirmLabel}
      confirmTitle={confirmTitle ?? "This action cannot be undone"}
      onConfirm={onClick}
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
  buttonProps: Omit<ButtonProps, "tier" | "onClick" | "children" | "confirmTitle" | "confirmDescription" | "confirmLabel" | "cancelLabel">;
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
        <ButtonBase {...buttonProps} type="button">
          {children}
        </ButtonBase>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        <PopoverHeader>
          <PopoverTitle>{confirmTitle}</PopoverTitle>
          {confirmDescription ? <PopoverDescription>{confirmDescription}</PopoverDescription> : null}
        </PopoverHeader>
        <div className="flex justify-end gap-2">
          <ButtonBase size="sm" type="button" variant="ghost" onClick={() => setOpen(false)}>
            {cancelLabel}
          </ButtonBase>
          <ButtonBase
            size="sm"
            type="button"
            variant="default"
            onClick={(e: MouseEvent<HTMLButtonElement>) => {
              setOpen(false);
              onConfirm?.(e);
            }}
          >
            {confirmLabel}
          </ButtonBase>
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
  buttonProps: Omit<ButtonProps, "tier" | "onClick" | "children" | "confirmTitle" | "confirmDescription" | "confirmLabel" | "cancelLabel">;
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
      <ButtonBase {...buttonProps} type="button" onClick={() => setOpen(true)}>
        {children}
      </ButtonBase>
      <Dialog onOpenChange={setOpen} open={open}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmTitle}</DialogTitle>
            {confirmDescription ? <DialogDescription>{confirmDescription}</DialogDescription> : null}
          </DialogHeader>
          <DialogFooter>
            <ButtonBase type="button" variant="ghost" onClick={() => setOpen(false)}>
              {cancelLabel}
            </ButtonBase>
            <ButtonBase
              type="button"
              variant="destructive"
              onClick={(e: MouseEvent<HTMLButtonElement>) => {
                setOpen(false);
                onConfirm?.(e);
              }}
            >
              {confirmLabel}
            </ButtonBase>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export { Button, ButtonBase, buttonVariants };
