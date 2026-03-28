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
        "relative flex w-px items-center justify-center bg-border after:absolute after:inset-y-0 after:left-1/2 after:-translate-x-1/2 after:w-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1",
        className,
      )}
      {...props}
    >
      {withHandle && (
        <div className="z-10 flex h-4 w-3 items-center justify-center rounded-sm border bg-border">
          <GripVertical className="h-2.5 w-2.5 text-muted-foreground" />
        </div>
      )}
    </ResizablePrimitive.Separator>
  );
}
