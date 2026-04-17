/**
 * Custom fetch function for Orval-generated clients.
 *
 * Injects the `Accept-Language` header from the current locale context
 * so the BFF returns locale-appropriate labels (see ADR-0013).
 *
 * Orval uses this as the `mutator` — both the fetch client and the
 * React Query hooks call customFetch with different signatures:
 *   - fetch client: customFetch(url: string, options) → { data, status, headers }
 *   - react-query hooks: customFetch({url, method, params, signal}, options) → data
 */
import { getCurrentLocale } from "@/lib/locale-context";

interface OrvalRequestConfig {
  url: string;
  method: string;
  params?: Record<string, unknown>;
  data?: unknown;
  signal?: AbortSignal;
}

function parseJsonBody(body: string | null): unknown {
  if (!body) {
    return {};
  }

  try {
    return JSON.parse(body);
  } catch {
    return { detail: body };
  }
}

export function parseApiResponseBody(body: string | null): unknown {
  return parseJsonBody(body);
}

export async function customFetch<T>(
  urlOrConfig: string | OrvalRequestConfig,
  options: RequestInit = {},
): Promise<T> {
  const locale = getCurrentLocale();

  let url: string;
  let init: RequestInit;

  if (typeof urlOrConfig === "string") {
    // Called from the fetch client: customFetch(url, { method, ... })
    url = urlOrConfig;
    init = {
      ...options,
      headers: {
        ...options.headers,
        "Accept-Language": locale,
      },
    };

    const res = await fetch(url, init);
    const body = [204, 205, 304].includes(res.status) ? null : await res.text();
    const data = parseJsonBody(body);
    return { data, status: res.status, headers: res.headers } as T;
  }

  // Called from react-query hooks: customFetch({ url, method, params, signal }, options)
  const { url: baseUrl, method, params, signal } = urlOrConfig;

  const searchParams = new URLSearchParams();
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    }
  }
  const queryString = searchParams.toString();
  url = queryString ? `${baseUrl}?${queryString}` : baseUrl;

  init = {
    ...options,
    method,
    signal,
    headers: {
      ...options.headers,
      "Accept-Language": locale,
    },
  };

  const res = await fetch(url, init);
  const body = [204, 205, 304].includes(res.status) ? null : await res.text();
  return parseJsonBody(body) as T;
}

export default customFetch;
