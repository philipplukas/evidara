export type CustomFetchConfig = {
  url: string;
  method: string;
  params?: Record<string, unknown>;
  signal?: AbortSignal;
  headers?: HeadersInit;
  data?: unknown;
};

function buildUrl(baseUrl: string, path: string, params?: Record<string, unknown>): string {
  const url = new URL(path, baseUrl);
  if (!params) {
    return url.toString();
  }

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) {
      continue;
    }
    url.searchParams.set(key, value === null ? "null" : String(value));
  }
  return url.toString();
}

export async function customFetch<T>({
  url,
  method,
  params,
  signal,
  headers,
  data,
}: CustomFetchConfig): Promise<T> {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:3001";
  const response = await fetch(buildUrl(apiBase, url, params), {
    method,
    signal,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: data === undefined ? undefined : JSON.stringify(data),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API request failed (${response.status}): ${body}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
