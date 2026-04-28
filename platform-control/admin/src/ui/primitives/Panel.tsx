"use client";

import type { CSSProperties, ReactNode } from "react";
import { cn } from "./cn";

export function Panel({
  children,
  id,
  testId,
  className,
  style,
  as: Component = "section",
}: {
  children: ReactNode;
  id?: string;
  testId?: string;
  className?: string;
  style?: CSSProperties;
  as?: "div" | "section" | "article";
}) {
  return (
    <Component
      id={id}
      data-testid={testId}
      style={style}
      className={cn(
        "rounded-lg border border-[var(--border)] bg-[var(--admin-panel-bg)]",
        "shadow-[var(--shadow-card)] backdrop-blur-[12px]",
        className,
      )}
    >
      {children}
    </Component>
  );
}
