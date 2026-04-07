"use client";

import { Clock, Lock, MapPin, Search, Settings2, SlidersHorizontal, User } from "lucide-react";
import { useTranslations } from "next-intl";
import { parseAsString, useQueryState } from "nuqs";
import { type FormEvent, useEffect, useState } from "react";
import { SUPPORTED_LOCALES, useLocale } from "@/lib/locale-context";
import { useWorkspace } from "@/lib/workspace-store";

interface AppHeaderProps {
  onOpenFilters?: () => void;
  onSearch?: (query: string) => Promise<void>;
  /** Set from server (profile + configured control-plane URL). */
  showControlPlaneEntry?: boolean;
  /** Set from server to avoid client-only build-time env coupling. */
  controlPanelUrl?: string;
}

export function AppHeader({
  onOpenFilters,
  onSearch,
  showControlPlaneEntry = true,
  controlPanelUrl,
}: AppHeaderProps) {
  const { state } = useWorkspace();
  const { locale, setLocale } = useLocale();
  const t = useTranslations();
  const [urlQuery, setUrlQuery] = useQueryState("q", parseAsString.withDefault(""));
  const storeQuery = state.resultSet.source.type === "search" ? state.resultSet.source.query : "";

  // Local input state — syncs with store query but allows free typing
  const [inputValue, setInputValue] = useState(storeQuery);
  const resolvedControlPanelUrl = controlPanelUrl?.trim();
  const hasControlPanelUrl = Boolean(resolvedControlPanelUrl);
  const hasControlPanelAccess = hasControlPanelUrl && showControlPlaneEntry;

  // Sync input when store query changes (e.g., from URL navigation)
  useEffect(() => {
    setInputValue(storeQuery);
  }, [storeQuery]);

  // On mount or when the URL ?q= param changes (e.g. browser back/forward),
  // resync the store search state if needed.
  useEffect(() => {
    if (!onSearch) return;
    if (urlQuery && urlQuery !== storeQuery) {
      void onSearch(urlQuery);
    }
  }, [urlQuery, storeQuery, onSearch]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed) return;

    if (onSearch) {
      await onSearch(trimmed);
    }
    await setUrlQuery(trimmed);
  };

  return (
    <header className="border-b border-border bg-surface-panel">
      <div className="flex items-center gap-6 px-6 py-3">
        {/* Wordmark */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-7 h-7 rounded-lg bg-brand-strong flex items-center justify-center">
            <span className="text-white font-bold text-sm">E</span>
          </div>
          <span className="text-lg font-semibold tracking-tight text-brand-strong">Evidara</span>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSubmit} className="flex-1 max-w-2xl">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={t("header.searchPlaceholder")}
              className="w-full h-10 pl-10 pr-4 rounded-lg border border-border bg-surface-input text-sm
                focus:outline-none focus:ring-2 focus:ring-focus-ring focus:border-brand
                placeholder:text-muted-foreground/60 transition-all"
            />
          </div>
        </form>

        {/* Navigation */}
        <nav className="flex items-center gap-1 shrink-0">
          {onOpenFilters && (
            <button
              type="button"
              onClick={onOpenFilters}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium
                text-muted-foreground hover:text-foreground hover:bg-muted transition-colors lg:hidden"
            >
              <SlidersHorizontal className="w-4 h-4" />
              {t("header.filters")}
            </button>
          )}
          <NavLink
            icon={<Clock className="w-4 h-4" />}
            label={t("header.trail")}
            count={state.trail.length > 0 ? state.trail.length : undefined}
          />
          <NavLink
            icon={<MapPin className="w-4 h-4" />}
            label={t("header.pinned")}
            count={state.pinned.length > 0 ? state.pinned.length : undefined}
          />
          {hasControlPanelAccess ? (
            <a
              href={resolvedControlPanelUrl!}
              target="_blank"
              rel="noreferrer noopener"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors border border-transparent
                text-muted-foreground hover:text-foreground hover:bg-muted hover:border-border"
            >
              <Settings2 className="w-4 h-4" />
              {t("header.controlPanel")}
            </a>
          ) : hasControlPanelUrl ? (
            <button
              type="button"
              disabled
              title={t("header.controlPanelRestricted")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border border-border/60
                text-muted-foreground/80 bg-muted/30 cursor-not-allowed"
            >
              <Lock className="w-4 h-4" />
              {t("header.controlPanel")}
            </button>
          ) : (
            <button
              type="button"
              disabled
              title={t("header.controlPanelUnavailable")}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border border-dashed border-border/70
                text-muted-foreground/80 bg-surface-panel cursor-not-allowed"
            >
              <Settings2 className="w-4 h-4" />
              {t("header.controlPanel")}
            </button>
          )}
        </nav>

        <div className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-muted/60 text-tiny font-semibold text-muted-foreground uppercase tracking-wider">
          <span>{t("header.profileLabel")}:</span>
          <span className={hasControlPanelAccess ? "text-brand" : "text-foreground/70"}>
            {hasControlPanelAccess ? t("header.profileOperator") : t("header.profileStandard")}
          </span>
        </div>

        {/* Locale Switcher */}
        {/* biome-ignore lint/a11y/useSemanticElements: fieldset would break flex layout styling */}
        <div
          className="flex items-center shrink-0"
          role="group"
          aria-label={t("header.languageGroup")}
        >
          {SUPPORTED_LOCALES.map((loc) => (
            <button
              key={loc}
              type="button"
              aria-pressed={locale === loc}
              onClick={() => setLocale(loc)}
              className={`px-2.5 py-1 text-xs font-semibold uppercase tracking-wider rounded-md transition-colors
                ${
                  locale === loc
                    ? "bg-brand text-white"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
            >
              {loc}
            </button>
          ))}
        </div>

        {/* User */}
        <div className="flex items-center gap-2 shrink-0 pl-2 border-l border-border">
          <button
            type="button"
            aria-label={t("header.openUserMenu")}
            className="w-8 h-8 rounded-full bg-interactive-accent-muted flex items-center justify-center
            hover:bg-brand/20 transition-colors"
          >
            <User className="w-4 h-4 text-brand" />
          </button>
        </div>
      </div>
    </header>
  );
}

function NavLink({
  icon,
  label,
  active,
  count,
}: {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  count?: number;
}) {
  return (
    <button
      type="button"
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors
        ${
          active
            ? "text-brand bg-interactive-accent-subtle"
            : "text-muted-foreground hover:text-foreground hover:bg-muted"
        }`}
    >
      {icon}
      {label}
      {count != null && (
        <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-interactive-accent-muted text-tiny font-semibold text-brand leading-none">
          {count}
        </span>
      )}
    </button>
  );
}
