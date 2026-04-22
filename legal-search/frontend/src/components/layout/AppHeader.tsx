"use client";

import {
  Bookmark,
  BookmarkCheck,
  Clock,
  HelpCircle,
  Loader2,
  Lock,
  MapPin,
  Search,
  Settings2,
  SlidersHorizontal,
  Trash2,
  User,
  X,
} from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { parseAsString, useQueryState } from "nuqs";
import { type FormEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { KeyboardShortcutsDialog } from "@/components/layout/KeyboardShortcutsDialog";
import { PreferencesDialog } from "@/components/layout/PreferencesDialog";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { ShareButton } from "@/components/ui/ShareButton";
import { useSavedSearches } from "@/hooks/use-saved-searches";
import { buildControlPanelHref } from "@/lib/control-plane-entry";
import { SUPPORTED_LOCALES, useLocale } from "@/lib/locale-context";
import { useWorkspace } from "@/lib/workspace-store";

const RECENT_QUERIES_STORAGE_KEY = "evidara.recent-queries";
const RECENT_QUERIES_LIMIT = 4;

const isKeyboardShortcutInputTarget = (target: EventTarget | null): boolean => {
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
  const [recentQueries, setRecentQueries] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const { savedSearches, saveSearch, removeSearch } = useSavedSearches();
  const searchInputRef = useRef<HTMLInputElement | null>(null);
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

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    try {
      const stored = window.localStorage.getItem(RECENT_QUERIES_STORAGE_KEY);
      if (!stored) {
        return;
      }

      const parsed = JSON.parse(stored);
      if (!Array.isArray(parsed)) {
        return;
      }

      setRecentQueries(
        parsed
          .filter((entry): entry is string => typeof entry === "string")
          .map((entry) => entry.trim())
          .filter(Boolean)
          .slice(0, RECENT_QUERIES_LIMIT),
      );
    } catch {
      // Ignore malformed storage and keep the search shell functional.
    }
  }, []);

  // On mount or when the URL ?q= param changes (e.g. browser back/forward),
  // resync the store search state if needed.
  useEffect(() => {
    if (!onSearch) return;
    if (urlQuery && urlQuery !== storeQuery) {
      void onSearch(urlQuery);
    }
  }, [urlQuery, storeQuery, onSearch]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.defaultPrevented ||
        event.key !== "/" ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey ||
        isKeyboardShortcutInputTarget(event.target)
      ) {
        return;
      }

      const input = searchInputRef.current;
      if (!input) {
        return;
      }

      event.preventDefault();
      input.focus();
      input.select();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const persistRecentQuery = (query: string) => {
    setRecentQueries((current) => {
      const next = [query, ...current.filter((entry) => entry !== query)].slice(
        0,
        RECENT_QUERIES_LIMIT,
      );

      if (typeof window !== "undefined") {
        try {
          window.localStorage.setItem(RECENT_QUERIES_STORAGE_KEY, JSON.stringify(next));
        } catch {
          // Ignore quota or privacy-mode failures.
        }
      }

      return next;
    });
  };

  const handleRunSearch = async (query: string) => {
    const trimmed = query.trim();
    if (!trimmed || isSearching) {
      return;
    }

    setIsSearching(true);
    setInputValue(trimmed);
    persistRecentQuery(trimmed);

    try {
      if (onSearch) {
        await onSearch(trimmed);
      }
      await setUrlQuery(trimmed);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await handleRunSearch(inputValue);
  };

  const handleRecentSearch = async (query: string) => {
    setInputValue(query);
    await handleRunSearch(query);
  };

  const handleSaveSearch = () => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    saveSearch({
      name: trimmed,
      query: trimmed,
      filters: { jurisdictions: [], languages: [], sourceType: null, officialOnly: false },
    });
  };

  const handleRestoreSavedSearch = async (query: string) => {
    setInputValue(query);
    await handleRunSearch(query);
  };

  const hasSearchText = inputValue.trim().length > 0;

  return (
    <>
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
            <div className="app-header__search-shell flex flex-col gap-2 rounded-3xl border border-border/70 bg-surface-input/95 p-2.5 shadow-inner transition-shadow focus-within:ring-2 focus-within:ring-focus-ring">
              <div className="flex items-center gap-2">
                <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
                <label htmlFor="evidara-search" className="sr-only">
                  Rechtsdokumente durchsuchen
                </label>
                <input
                  ref={searchInputRef}
                  id="evidara-search"
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder={t("header.searchPlaceholder")}
                  aria-describedby={
                    recentQueries.length > 0 ? "app-header-search-recent" : undefined
                  }
                  aria-keyshortcuts="/"
                  className="h-10 min-w-0 flex-1 border-0 bg-transparent px-0 text-sm text-foreground outline-none placeholder:text-muted-foreground/60 focus:ring-0"
                />
                {hasSearchText && (
                  <button
                    type="button"
                    onClick={() => setInputValue("")}
                    className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/60 text-muted-foreground transition-colors hover:border-border hover:bg-muted hover:text-foreground"
                    aria-label={t("header.clearSearch")}
                    title={t("header.clearSearch")}
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
                <button
                  type="submit"
                  disabled={!hasSearchText || isSearching}
                  aria-busy={isSearching}
                  className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-primary px-3.5 text-sm font-semibold text-white transition-colors hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-50 sm:px-4"
                >
                  {isSearching ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                  <span className="sr-only sm:not-sr-only">
                    {isSearching ? t("header.searchingAction") : t("header.searchAction")}
                  </span>
                </button>
                {hasSearchText && (
                  <button
                    type="button"
                    onClick={handleSaveSearch}
                    className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/60 text-muted-foreground transition-colors hover:border-accent-core/30 hover:bg-interactive-accent-subtle hover:text-accent-core"
                    aria-label={t("header.saveSearch")}
                    title={t("header.saveSearch")}
                  >
                    <Bookmark className="h-4 w-4" />
                  </button>
                )}
              </div>

              {recentQueries.length > 0 && (
                <fieldset
                  id="app-header-search-recent"
                  className="flex flex-wrap items-center gap-1.5 px-1 text-[11px] text-muted-foreground/80"
                >
                  <legend className="sr-only">{t("header.recentSearches")}</legend>
                  <Clock className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
                  {recentQueries.map((query) => (
                    <button
                      type="button"
                      key={query}
                      onClick={() => void handleRecentSearch(query)}
                      className="inline-flex items-center rounded-full border border-border/60 bg-surface-panel px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:border-accent-core/30 hover:bg-interactive-accent-subtle hover:text-accent-core"
                    >
                      {query}
                    </button>
                  ))}
                </fieldset>
              )}

              {savedSearches.length > 0 && (
                <fieldset className="flex flex-wrap items-center gap-1.5 px-1 text-[11px] text-muted-foreground/80">
                  <legend className="sr-only">{t("header.savedSearches")}</legend>
                  <BookmarkCheck className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
                  {savedSearches.map((saved) => (
                    <span
                      key={saved.id}
                      className="inline-flex items-center rounded-full border border-border/60 bg-surface-panel text-xs font-medium text-foreground transition-colors hover:border-accent-core/30 hover:bg-interactive-accent-subtle"
                    >
                      <button
                        type="button"
                        onClick={() => void handleRestoreSavedSearch(saved.query)}
                        className="inline-flex items-center gap-1 py-1 pl-2.5 pr-1 hover:text-accent-core"
                        title={t("header.restoreSavedSearch")}
                      >
                        <Bookmark className="h-3 w-3 shrink-0" />
                        {saved.name}
                      </button>
                      <button
                        type="button"
                        onClick={() => removeSearch(saved.id)}
                        className="inline-flex items-center justify-center rounded-r-full py-1 pl-0.5 pr-2 text-muted-foreground hover:text-destructive"
                        aria-label={t("header.removeSavedSearch")}
                        title={t("header.removeSavedSearch")}
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </fieldset>
              )}
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
              <a href={controlPlaneHref} className="app-header__control-plane">
                <span className="app-header__control-plane-icon">
                  <Settings2 className="h-3.5 w-3.5" />
                </span>
                <span className="app-header__control-plane-copy">
                  <span className="app-header__control-plane-text">{t("header.controlPanel")}</span>
                </span>
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

            <ThemeToggle />
            <ShareButton size="sm" className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0" />
            <PreferencesDialog>
              <button
                type="button"
                aria-label={t("header.openSettings")}
                title={t("header.openSettings")}
                className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 rounded-md px-2.5 py-1 text-xs font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <Settings2 className="h-4 w-4" />
              </button>
            </PreferencesDialog>
            <button
              type="button"
              onClick={() => setShowShortcuts(true)}
              aria-label={t("header.openKeyboardShortcuts")}
              title={t("header.openKeyboardShortcuts")}
              className="min-h-11 min-w-11 sm:min-h-0 sm:min-w-0 rounded-md px-2.5 py-1 text-xs font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <HelpCircle className="h-4 w-4" />
            </button>

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
                      ? "bg-accent-core text-white"
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
                className="flex h-8 w-8 items-center justify-center rounded-full bg-interactive-accent-muted transition-colors hover:bg-accent-core/20"
              >
                <User className="h-4 w-4 text-accent-core" />
              </button>
            </div>
          </div>
        </div>
      </header>
      <KeyboardShortcutsDialog open={showShortcuts} onOpenChange={setShowShortcuts} />
    </>
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
        <span className="ml-0.5 rounded-full bg-accent-core-subtle px-1.5 py-0.5 text-tiny font-semibold leading-none text-accent-core">
          {count}
        </span>
      )}
    </button>
  );
}
