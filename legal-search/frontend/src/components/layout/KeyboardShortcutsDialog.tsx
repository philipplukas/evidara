"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const isInputTarget = (target: EventTarget | null): boolean => {
  if (!target || typeof target !== "object") {
    return false;
  }

  const element = target as {
    tagName?: string;
    isContentEditable?: boolean;
    contentEditable?: string;
    closest?: (selector: string) => unknown;
  };

  const tagName = element.tagName?.toUpperCase();

  return (
    tagName === "INPUT" ||
    tagName === "TEXTAREA" ||
    tagName === "SELECT" ||
    element.isContentEditable === true ||
    element.contentEditable === "true" ||
    (typeof element.closest === "function" && element.closest("[contenteditable='true']") !== null)
  );
};

interface ShortcutEntry {
  keys: string[];
  labelKey: string;
}

const SHORTCUTS: ShortcutEntry[] = [
  { keys: ["/"], labelKey: "help.shortcuts.focusSearch" },
  { keys: ["Esc"], labelKey: "help.shortcuts.closePanels" },
  { keys: ["\u2191", "\u2193"], labelKey: "help.shortcuts.navigateResults" },
  { keys: ["Enter"], labelKey: "help.shortcuts.selectResult" },
  { keys: ["?"], labelKey: "help.shortcuts.openHelp" },
];

interface KeyboardShortcutsDialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function KeyboardShortcutsDialog({
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
}: KeyboardShortcutsDialogProps) {
  const t = useTranslations();
  const [internalOpen, setInternalOpen] = useState(false);

  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;
  const setOpen = useCallback(
    (value: boolean) => {
      if (isControlled) {
        controlledOnOpenChange?.(value);
      } else {
        setInternalOpen(value);
      }
    },
    [isControlled, controlledOnOpenChange],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.defaultPrevented ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        isInputTarget(event.target)
      ) {
        return;
      }

      if (event.key === "?") {
        event.preventDefault();
        setOpen(!open);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, setOpen]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("help.shortcuts.title")}</DialogTitle>
          <DialogDescription>{t("help.shortcuts.description")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          {SHORTCUTS.map((shortcut) => (
            <div
              key={shortcut.labelKey}
              className="flex items-center justify-between rounded-lg px-2 py-2 transition-colors hover:bg-muted/40"
            >
              <span className="text-sm text-foreground">{t(shortcut.labelKey)}</span>
              <span className="flex items-center gap-1">
                {shortcut.keys.map((key) => (
                  <kbd
                    key={key}
                    className="inline-flex h-6 min-w-6 items-center justify-center rounded-md border border-border bg-muted px-1.5 font-mono text-xs font-medium text-muted-foreground"
                  >
                    {key}
                  </kbd>
                ))}
              </span>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
