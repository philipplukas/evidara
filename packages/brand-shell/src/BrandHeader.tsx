import type { CSSProperties, ReactNode } from "react";

interface BrandHeaderProps {
  /**
   * Header content. Each surface arranges its own layout — workspace
   * uses a grid-template-areas pattern (brand / search / nav / utility);
   * admin uses a flex shell (brand / title block / back-CTA). The shared
   * component intentionally does not opine on the inner arrangement
   * because ADR-0027 records the two surfaces as "two products, shared
   * brand" with intentionally divergent surface chrome.
   */
  children: ReactNode;
  /**
   * Class applied to the root `<header>` element. Each surface
   * supplies its own background, border, and shadow tokens.
   */
  className?: string;
  /**
   * Optional inner-wrapper class. When supplied, the children are
   * rendered inside an extra `<div>` with this class — used by
   * surfaces (workspace, admin) that compose a separate inner
   * container (`.app-header__inner`, etc.) for their grid / flex
   * layout.
   */
  innerClassName?: string;
  style?: CSSProperties;
}

export function BrandHeader({
  children,
  className,
  innerClassName,
  style,
}: BrandHeaderProps) {
  const inner = innerClassName ? (
    <div data-evidara-brand-header-inner className={innerClassName}>
      {children}
    </div>
  ) : (
    children
  );

  return (
    <header data-evidara-brand-header className={className} style={style}>
      {inner}
    </header>
  );
}
