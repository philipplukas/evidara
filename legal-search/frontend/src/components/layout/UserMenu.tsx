"use client";

import { Check, Link as LinkIcon, Moon, Sun, User } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useCallback, useRef, useState } from "react";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useThemePreference } from "@/hooks/use-theme-preference";
import { AnalyticsEvent, track } from "@/lib/analytics";
import { formatBuildLabel, getBuildInfo } from "@/lib/build-info";
import { SUPPORTED_LOCALES, useLocale } from "@/lib/locale-context";

interface UserMenuProps {
  /** Whether the current session has operator-tier control-plane access. */
  hasControlPanelAccess: boolean;
}

/**
 * Avatar dropdown that surfaces preference-grade controls (theme, language,
 * share, profile mode) from a single tap target. On mobile this replaces the
 * dense utility strip; on desktop it lives alongside the inline controls so
 * dark-mode and language are reachable from both breakpoints (#390, #391).
 */
export function UserMenu({ hasControlPanelAccess }: UserMenuProps) {
  const tHeader = useTranslations("header");
  const tTheme = useTranslations("theme");
  const tShare = useTranslations("share");
  const tMenu = useTranslations("userMenu");
  const { theme, mounted, toggle: toggleTheme } = useThemePreference();
  const { locale, setLocale } = useLocale();
  // Module-level constants underneath, so this is a plain read, not state.
  const buildInfo = getBuildInfo();

  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopyLink = useCallback(() => {
    const target = window.location.href;
    void navigator.clipboard.writeText(target);
    track(AnalyticsEvent.SHARE_LINK_COPIED, { url: target, context: "user_menu" });
    setCopied(true);
    if (copyTimer.current) clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => setCopied(false), 2000);
  }, []);

  const themeLabel = theme === "dark" ? tTheme("switchToLight") : tTheme("switchToDark");
  const profileLabel = hasControlPanelAccess
    ? tHeader("profileOperator")
    : tHeader("profileStandard");

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={tHeader("openUserMenu")}
          className="flex h-11 w-11 sm:h-8 sm:w-8 shrink-0 items-center justify-center rounded-full bg-interactive-accent-muted transition-colors hover:bg-accent-core/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          <User className="h-4 w-4 text-accent-core" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={6} className="w-64">
        <PopoverHeader>
          <PopoverTitle>{tMenu("title")}</PopoverTitle>
          <PopoverDescription>
            <span className="font-semibold uppercase tracking-wider">
              {tHeader("profileLabel")}:
            </span>{" "}
            <span className={hasControlPanelAccess ? "text-brand" : ""}>{profileLabel}</span>
          </PopoverDescription>
        </PopoverHeader>

        <MenuRow label={tMenu("themeLabel")}>
          {mounted ? (
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={themeLabel}
              className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border/60 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
            >
              {theme === "dark" ? (
                <>
                  <Sun className="h-3.5 w-3.5" />
                  {tMenu("themeDark")}
                </>
              ) : (
                <>
                  <Moon className="h-3.5 w-3.5" />
                  {tMenu("themeLight")}
                </>
              )}
            </button>
          ) : (
            <span aria-hidden className="inline-flex h-9 w-20 rounded-md" />
          )}
        </MenuRow>

        <MenuRow label={tMenu("languageLabel")}>
          {/* biome-ignore lint/a11y/useSemanticElements: fieldset would break flex layout styling */}
          <div role="group" aria-label={tHeader("languageGroup")} className="inline-flex gap-1">
            {SUPPORTED_LOCALES.map((loc) => (
              <button
                key={loc}
                type="button"
                aria-pressed={locale === loc}
                onClick={() => setLocale(loc)}
                className={`min-h-9 rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-wider transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring ${
                  locale === loc
                    ? "bg-accent-core text-white"
                    : "border border-border/60 text-foreground hover:bg-muted"
                }`}
              >
                {loc}
              </button>
            ))}
          </div>
        </MenuRow>

        <MenuRow label={tMenu("shareLabel")}>
          <button
            type="button"
            onClick={handleCopyLink}
            aria-label={copied ? tShare("linkCopied") : tShare("copyLink")}
            className={`inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border/60 px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring ${
              copied
                ? "border-success/40 bg-success/10 text-success"
                : "text-foreground hover:bg-muted"
            }`}
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <LinkIcon className="h-3.5 w-3.5" />}
            {copied ? tShare("linkCopied") : tShare("copyLink")}
          </button>
        </MenuRow>

        {/*
          Build provenance. Renders only when the bundle was built from a tagged
          image — `getBuildInfo()` is null under `npm run dev`, and an empty
          version line reads as "no version" rather than "not applicable".

          Deliberately not translated: a commit SHA and an ISO date are the same
          in every locale, and routing them through i18n would imply otherwise.
        */}
        {buildInfo ? (
          <div className="border-t border-border/60 pt-2">
            <a
              href={buildInfo.commitUrl}
              target="_blank"
              rel="noreferrer"
              title={buildInfo.sha}
              className="font-mono text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              {formatBuildLabel(buildInfo)}
            </a>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

function MenuRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      {children}
    </div>
  );
}
