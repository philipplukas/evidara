"use client";

import { GripVertical } from "lucide-react";
import * as ResizablePrimitive from "react-resizable-panels";
import { cn } from "@/lib/utils";

// Re-export types for downstream consumers
export type { PanelImperativeHandle } from "react-resizable-panels";

type Orientation = "horizontal" | "vertical";

export function ResizablePanelGroup({
  className,
  direction,
  ...props
}: Omit<React.ComponentProps<typeof ResizablePrimitive.Group>, "orientation"> & {
  direction?: Orientation;
}) {
  return (
    <ResizablePrimitive.Group
      className={cn("flex h-full w-full", className)}
      orientation={direction}
      {...props}
    />
  );
}

export function ResizablePanel({
  className,
  panelRef,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.Panel>) {
  return <ResizablePrimitive.Panel className={cn("", className)} panelRef={panelRef} {...props} />;
}

/**
 * Layout width the separator occupies in the panel row, in px.
 *
 * The separator used to be `w-px`, which gave it a **1 physical pixel** hit
 * target — unhittable with a trackpad and far below WCAG 2.5.5/2.5.8 target
 * size (see #679). It is now a real {@link RESIZE_HANDLE_HIT_AREA_PX}-wide
 * interactive element whose horizontal margins pull it back to the same 1px of
 * layout, so panel geometry is byte-identical to before while the grab area is
 * 17x the size. The visible rule is drawn by a centered 1px `::before`.
 */
export const RESIZE_HANDLE_HIT_AREA_PX = 17;

export function ResizableHandle({
  withHandle,
  className,
  ...props
}: React.ComponentProps<typeof ResizablePrimitive.Separator> & {
  withHandle?: boolean;
}) {
  return (
    <ResizablePrimitive.Separator
      className={cn(
        // 17px wide, -8px on each side => 1px of net layout width (unchanged).
        "group relative -mx-2 flex w-[17px] shrink-0 cursor-col-resize items-center justify-center bg-transparent",
        // The visible 1px rule, centered inside the wide hit area.
        "before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-border before:transition-colors",
        "hover:before:bg-accent-core focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1",
        className,
      )}
      {...props}
    >
      {withHandle && (
        <div className="z-10 flex h-8 w-3 items-center justify-center rounded-sm border border-border bg-surface-panel shadow-sm transition-colors group-hover:border-accent-core">
          <GripVertical className="h-3 w-3 text-muted-foreground" />
        </div>
      )}
    </ResizablePrimitive.Separator>
  );
}
