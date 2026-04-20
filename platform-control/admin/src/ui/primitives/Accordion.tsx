/**
 * `Accordion` — radix-based disclosure primitive, zero MUI.
 *
 * Built on `@radix-ui/react-accordion` so keyboard navigation, focus
 * management, and ARIA semantics come from a well-tested upstream.
 * Styled to match the card chrome of `DetailGrid` / `DataTable` so
 * stacks of sections render as a consistent column of cards.
 *
 * Usage:
 *   <AccordionRoot type="multiple" defaultValue={["pipeline-health"]}>
 *     <AccordionItem value="provider-jobs">
 *       <AccordionTrigger>
 *         Provider Jobs <Pill variant="meta">{n}</Pill>
 *       </AccordionTrigger>
 *       <AccordionContent>...</AccordionContent>
 *     </AccordionItem>
 *   </AccordionRoot>
 *
 * The chevron rotates via `data-[state=open]`, and the content panel
 * animates open/closed using CSS keyframes that read the radix-exposed
 * `--radix-accordion-content-height` custom property. All motion is
 * gated on `@media (prefers-reduced-motion: no-preference)` so users
 * who opt out of animation get instant state changes.
 */
"use client";

import * as RadixAccordion from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";
import { type ComponentPropsWithoutRef, type ElementRef, forwardRef, type ReactNode } from "react";
import { cn } from "./cn";

/**
 * `AccordionRoot` forwards to radix's `Root`. Radix splits `Root` into a
 * `type: "single"` vs `type: "multiple"` discriminated union; we re-export the
 * upstream component directly so TypeScript keeps narrowing on the caller's
 * `type` prop (single → `value: string`, multiple → `value: string[]`).
 * A wrapper `className` layer adds the default column gap used by the admin.
 */
type AccordionRootProps = ComponentPropsWithoutRef<typeof RadixAccordion.Root>;

export const AccordionRoot = forwardRef<ElementRef<typeof RadixAccordion.Root>, AccordionRootProps>(
  ({ className, ...rest }, ref) => {
    return (
      <RadixAccordion.Root ref={ref} {...rest} className={cn("flex flex-col gap-3", className)} />
    );
  },
);
AccordionRoot.displayName = "AccordionRoot";

export const AccordionItem = forwardRef<
  ElementRef<typeof RadixAccordion.Item>,
  ComponentPropsWithoutRef<typeof RadixAccordion.Item>
>(({ className, children, ...rest }, ref) => {
  return (
    <RadixAccordion.Item
      ref={ref}
      {...rest}
      className={cn(
        "rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-white/85",
        "shadow-[var(--shadow-card)] backdrop-blur-[12px] overflow-hidden",
        className,
      )}
    >
      {children}
    </RadixAccordion.Item>
  );
});
AccordionItem.displayName = "AccordionItem";

interface AccordionTriggerProps extends ComponentPropsWithoutRef<typeof RadixAccordion.Trigger> {
  children: ReactNode;
}

export const AccordionTrigger = forwardRef<
  ElementRef<typeof RadixAccordion.Trigger>,
  AccordionTriggerProps
>(({ className, children, ...rest }, ref) => {
  return (
    <RadixAccordion.Header className="flex">
      <RadixAccordion.Trigger
        ref={ref}
        {...rest}
        className={cn(
          "group flex w-full items-center justify-between gap-3 px-5 py-4 text-left",
          "text-[15px] font-semibold text-[var(--foreground)] leading-tight",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px]",
          "focus-visible:outline-[var(--brand-focus-ring)]",
          "hover:bg-[var(--brand-wash-3)] transition-colors",
          className,
        )}
      >
        <span className="flex items-center gap-2 min-w-0">{children}</span>
        <ChevronDown
          size={16}
          strokeWidth={2.5}
          aria-hidden
          className={cn(
            "shrink-0 text-[rgba(29,41,61,0.6)]",
            "transition-transform duration-200 ease-[cubic-bezier(0.4,0,0.2,1)]",
            "group-data-[state=open]:rotate-180",
            "motion-reduce:transition-none",
          )}
        />
      </RadixAccordion.Trigger>
    </RadixAccordion.Header>
  );
});
AccordionTrigger.displayName = "AccordionTrigger";

export const AccordionContent = forwardRef<
  ElementRef<typeof RadixAccordion.Content>,
  ComponentPropsWithoutRef<typeof RadixAccordion.Content>
>(({ className, children, ...rest }, ref) => {
  return (
    <RadixAccordion.Content
      ref={ref}
      {...rest}
      className={cn(
        // Radix exposes `--radix-accordion-content-height` so CSS can
        // animate from 0 → content-height on open. The keyframes live
        // in `globals.css` so they ship once and respect the global
        // `prefers-reduced-motion` media query.
        "overflow-hidden border-t border-[rgba(29,41,61,0.06)]",
        "data-[state=open]:animate-[accordion-open_200ms_cubic-bezier(0.4,0,0.2,1)]",
        "data-[state=closed]:animate-[accordion-closed_200ms_cubic-bezier(0.4,0,0.2,1)]",
        "motion-reduce:!animate-none",
        className,
      )}
    >
      <div className="px-5 py-4">{children}</div>
    </RadixAccordion.Content>
  );
});
AccordionContent.displayName = "AccordionContent";
