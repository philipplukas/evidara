"use client";

import {
  ArrowUpRight,
  Clock,
  Lock,
  MapPin,
  Search,
  Settings2,
  SlidersHorizontal,
  User,
} from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { parseAsString, useQueryState } from "nuqs";
import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { buildControlPanelHref } from "@/lib/control-plane-entry";
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
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [urlQuery, setUrlQuery] = useQueryState("q", parseAsString.withDefault(""));
  const [selectedId] = useQueryState("item", parseAsString);
  const storeQuery = state.resultSet.source.type === "search" ? state.resultSet.source.query : "";

  // Local input state — syncs with store query but allows free typing
  const [inputValue, setInputValue] = useState(storeQuery);
  const resolvedControlPanelUrl = controlPanelUrl?.trim();
  const hasControlPanelUrl = Boolean(resolvedControlPanelUrl);
  const hasControlPanelAccess = hasControlPanelUrl && showControlPlaneEntry;
  const returnToUrl = useMemo(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const queryString = searchParams?.toString() ?? "";
    const suffix = queryString ? `?${queryString}` : "";
    return `${window.location.origin}${pathname}${suffix}`;
  }, [pathname, searchParams]);
  const controlPlaneHref = hasControlPanelAccess
    ? (buildControlPanelHref({
        controlPanelUrl: resolvedControlPanelUrl,
        returnTo: returnToUrl,
        query: urlQuery || storeQuery,
        scopeLabel: state.resultSet.scopeLabel,
        selectedId,
      }) ?? resolvedControlPanelUrl)
    : resolvedControlPanelUrl;

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
    <header className="app-header">
      <div className="app-header__inner">
        {/* Wordmark */}
        <div className="app-header__brand">
          <div className="app-header__brand-mark">
            <span className="text-white font-bold text-sm">E</span>
          </div>
          <span className="app-header__brand-name">Evidara</span>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSubmit} className="app-header__search">
          <div className="app-header__search-shell">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={t("header.searchPlaceholder")}
              className="app-header__search-input"
            />
          </div>
        </form>

        {/* Navigation */}
        <nav className="app-header__nav">
          {onOpenFilters && (
            <button
              type="button"
              onClick={onOpenFilters}
              className="app-header__nav-button app-header__nav-button--idle lg:hidden"
            >
              <SlidersHorizontal className="h-4 w-4" />
              {t("header.filters")}
            </button>
          )}
          <NavLink
            icon={<Clock className="h-4 w-4" />}
            label={t("header.trail")}
            count={state.trail.length > 0 ? state.trail.length : undefined}
          />
          <NavLink
            icon={<MapPin className="h-4 w-4" />}
            label={t("header.pinned")}
            count={state.pinned.length > 0 ? state.pinned.length : undefined}
          />
          {hasControlPanelAccess ? (
            <a
              href={controlPlaneHref}
              target="_blank"
              rel="noreferrer noopener"
              className="app-header__control-plane"
            >
              <span className="app-header__control-plane-icon">
                <Settings2 className="h-4 w-4" />
              </span>
              <span className="app-header__control-plane-copy">
                <span className="app-header__control-plane-kicker">
                  {t("header.profileOperator")}
                </span>
                <span className="app-header__control-plane-text">{t("header.controlPanel")}</span>
              </span>
              <ArrowUpRight className="h-3.5 w-3.5 shrink-0" />
            </a>
          ) : hasControlPanelUrl ? (
            <button
              type="button"
              disabled
              title={t("header.controlPanelRestricted")}
              className="app-header__nav-button cursor-not-allowed border border-border/60 bg-muted/30 text-muted-foreground/80"
            >
              <Lock className="h-4 w-4" />
              {t("header.controlPanel")}
            </button>
          ) : (
            <button
              type="button"
              disabled
              title={t("header.controlPanelUnavailable")}
              className="app-header__nav-button cursor-not-allowed border border-dashed border-border/70 bg-surface-panel text-muted-foreground/80"
            >
              <Settings2 className="h-4 w-4" />
              {t("header.controlPanel")}
            </button>
          )}
        </nav>

        <div className="app-header__utility-strip">
          <div className="app-header__status">
            <span>{t("header.profileLabel")}:</span>
            <span className={hasControlPanelAccess ? "text-brand" : "text-foreground/70"}>
              {hasControlPanelAccess ? t("header.profileOperator") : t("header.profileStandard")}
            </span>
          </div>

          {/* Locale Switcher */}
          {/* biome-ignore lint/a11y/useSemanticElements: fieldset would break flex layout styling */}
          <div
            className="flex shrink-0 items-center"
            role="group"
            aria-label={t("header.languageGroup")}
          >
            {SUPPORTED_LOCALES.map((loc) => (
              <button
                key={loc}
                type="button"
                aria-pressed={locale === loc}
                onClick={() => setLocale(loc)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold uppercase tracking-wider transition-colors
                  ${
                    locale === loc
                      ? "bg-brand text-white"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
              >
                {loc}
              </button>
            ))}
          </div>

          {/* User */}
          <div className="flex shrink-0 items-center gap-2 border-l border-border/60 pl-2">
            <button
              type="button"
              aria-label={t("header.openUserMenu")}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-interactive-accent-muted transition-colors hover:bg-brand/20"
            >
              <User className="h-4 w-4 text-brand" />
            </button>
          </div>
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
  icon: ReactNode;
  label: string;
  active?: boolean;
  count?: number;
}) {
  return (
    <button
      type="button"
      className={`app-header__nav-button transition-colors ${
        active ? "app-header__nav-button--active" : "app-header__nav-button--idle"
      }`}
    >
      {icon}
      {label}
      {count != null && (
        <span className="ml-0.5 rounded-full bg-interactive-accent-muted px-1.5 py-0.5 text-tiny font-semibold leading-none text-brand">
          {count}
        </span>
      )}
    </button>
  );
}
