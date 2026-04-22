/**
 * Lightweight analytics event tracking foundation.
 *
 * Provider-agnostic: logs to console in development, queues events for
 * a configurable backend (Plausible, PostHog, etc.) in production.
 * No external dependencies required.
 */

// ─── Event Names ───

export const AnalyticsEvent = {
  SEARCH_EXECUTED: "search.executed",
  RESULT_SELECTED: "result.selected",
  RESULT_PIVOTED: "result.pivoted",
  FILTER_APPLIED: "filter.applied",
  FILTER_REMOVED: "filter.removed",
  DETAIL_TAB_CHANGED: "detail.tab_changed",
  PIN_ADDED: "pin.added",
  PIN_REMOVED: "pin.removed",
  SHARE_LINK_COPIED: "share.link_copied",
  PAGE_VIEW: "page.view",
} as const;

export type AnalyticsEventName = (typeof AnalyticsEvent)[keyof typeof AnalyticsEvent];

// ─── Property types per event ───

export interface AnalyticsEventProperties {
  [AnalyticsEvent.SEARCH_EXECUTED]: {
    query: string;
    resultCount: number;
    jurisdictions?: string;
    languages?: string;
  };
  [AnalyticsEvent.RESULT_SELECTED]: {
    resultId: string;
    resultType?: string;
    position?: number;
  };
  [AnalyticsEvent.RESULT_PIVOTED]: {
    sourceId: string;
    label: string;
  };
  [AnalyticsEvent.FILTER_APPLIED]: {
    filterType: string;
    value: string;
  };
  [AnalyticsEvent.FILTER_REMOVED]: {
    filterType: string;
    value?: string;
  };
  [AnalyticsEvent.DETAIL_TAB_CHANGED]: {
    tab: string;
    previousTab?: string;
  };
  [AnalyticsEvent.PIN_ADDED]: {
    itemId: string;
    itemType?: string;
  };
  [AnalyticsEvent.PIN_REMOVED]: {
    itemId: string;
  };
  [AnalyticsEvent.SHARE_LINK_COPIED]: {
    url?: string;
    context?: string;
  };
  [AnalyticsEvent.PAGE_VIEW]: {
    path: string;
    referrer?: string;
  };
}

// ─── Provider interface ───

export interface AnalyticsProvider {
  track(event: string, properties?: Record<string, unknown>): void;
  /** Optional: called once when the provider is registered. */
  init?(): void;
}

// ─── Internal state ───

let _providers: AnalyticsProvider[] = [];
let _queue: Array<{ event: string; properties?: Record<string, unknown>; timestamp: number }> = [];

const isDev = typeof process !== "undefined" && process.env?.NODE_ENV === "development";

// ─── Public API ───

/**
 * Track an analytics event. Type-safe: event names and their properties
 * are validated at compile time.
 *
 * In development, events are logged to the console.
 * In production, events are forwarded to registered providers or queued
 * until a provider is registered.
 */
export function track<E extends AnalyticsEventName>(
  event: E,
  properties?: AnalyticsEventProperties[E],
): void {
  if (typeof window === "undefined") return;

  const props = properties as Record<string, unknown> | undefined;

  if (isDev) {
    console.log(`[analytics] ${event}`, props ?? "");
    return;
  }

  if (_providers.length === 0) {
    // No provider yet — queue for later flush
    _queue.push({ event, properties: props, timestamp: Date.now() });
    // Cap queue to prevent unbounded growth before a provider is registered
    if (_queue.length > 500) {
      _queue = _queue.slice(-500);
    }
    return;
  }

  for (const provider of _providers) {
    try {
      provider.track(event, props);
    } catch {
      // Silently swallow — analytics must never break the app
    }
  }
}

/**
 * Register an analytics provider (e.g. Plausible, PostHog).
 * Flushes any queued events that were tracked before the provider was ready.
 */
export function registerProvider(provider: AnalyticsProvider): void {
  provider.init?.();
  _providers.push(provider);

  // Flush queued events
  const pending = _queue;
  _queue = [];
  for (const entry of pending) {
    try {
      provider.track(entry.event, entry.properties);
    } catch {
      // Silently swallow
    }
  }
}

/**
 * Remove all registered providers. Useful for tests.
 */
export function resetAnalytics(): void {
  _providers = [];
  _queue = [];
}
