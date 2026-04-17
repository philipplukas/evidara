"use client";

import {
  Button,
  type ButtonProps,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Popover,
  Stack,
  Typography,
} from "@mui/material";
import { type MouseEvent, type ReactNode, useRef, useState } from "react";

export type ConsequenceTier = "safe" | "notable" | "destructive";

interface ConfirmButtonProps extends Omit<ButtonProps, "onClick"> {
  tier?: ConsequenceTier;
  confirmTitle?: string;
  confirmDescription?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void | Promise<void>;
  children: ReactNode;
}

export function ConfirmButton({
  tier = "safe",
  confirmTitle,
  confirmDescription,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  children,
  ...buttonProps
}: ConfirmButtonProps) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);

  if (tier === "safe") {
    return (
      <Button
        {...buttonProps}
        onClick={(e) => {
          e.stopPropagation();
          void onConfirm();
        }}
      >
        {children}
      </Button>
    );
  }

  if (tier === "notable") {
    return (
      <>
        <Button
          ref={anchorRef}
          {...buttonProps}
          onClick={(e: MouseEvent) => {
            e.stopPropagation();
            setOpen(true);
          }}
        >
          {children}
        </Button>
        <Popover
          open={open}
          anchorEl={anchorRef.current}
          onClose={() => setOpen(false)}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
          transformOrigin={{ vertical: "top", horizontal: "center" }}
          slotProps={{ paper: { sx: { p: 2, maxWidth: 280 } } }}
        >
          <Stack spacing={1.5}>
            <Typography variant="subtitle2">{confirmTitle ?? "Are you sure?"}</Typography>
            {confirmDescription && (
              <Typography variant="body2" color="text.secondary">
                {confirmDescription}
              </Typography>
            )}
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button size="small" onClick={() => setOpen(false)}>
                {cancelLabel}
              </Button>
              <Button
                size="small"
                variant="contained"
                onClick={() => {
                  setOpen(false);
                  void onConfirm();
                }}
              >
                {confirmLabel}
              </Button>
            </Stack>
          </Stack>
        </Popover>
      </>
    );
  }

  return (
    <>
      <Button
        {...buttonProps}
        onClick={(e: MouseEvent) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        {children}
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs">
        <DialogTitle>{confirmTitle ?? "This action cannot be undone"}</DialogTitle>
        {confirmDescription && (
          <DialogContent>
            <DialogContentText>{confirmDescription}</DialogContentText>
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{cancelLabel}</Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => {
              setOpen(false);
              void onConfirm();
            }}
          >
            {confirmLabel}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
