/**
 * Orval mutator for Document Service calls.
 * Orval passes `(path, init)` and expects a return value shaped like `{ data, status, headers }`.
 *
 * Base URL and optional API key come from the environment (Nest ConfigModule loads `.env`).
 */

export class DocumentIntelligenceHttpError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'DocumentIntelligenceHttpError';
    this.status = status;
  }
}

export const documentIntelligenceFetch = async <T>(path: string, init: RequestInit): Promise<T> => {
  const rawBase = process.env.DOCUMENT_INTELLIGENCE_BASE_URL?.trim() ?? '';
  const base = rawBase.replace(/\/$/, '');
  if (!base) {
    throw new Error('DOCUMENT_INTELLIGENCE_BASE_URL is not set');
  }

  const apiKey = process.env.DOCUMENT_INTELLIGENCE_API_KEY?.trim();
  const headers = new Headers(init.headers);
  if (!headers.has('Accept')) {
    headers.set('Accept', path.endsWith('/text') ? 'text/plain,*/*;q=0.8' : 'application/json');
  }
  if (apiKey) {
    headers.set('Authorization', `Bearer ${apiKey}`);
  }

  const res = await fetch(`${base}${path}`, {
    ...init,
    headers,
  });

  const responseHeaders = res.headers;
  const ct = res.headers.get('content-type') ?? '';

  if (res.status === 404) {
    const data = ct.includes('json') ? await res.json() : await res.text();
    return { data, status: 404, headers: responseHeaders } as T;
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new DocumentIntelligenceHttpError(
      res.status,
      text
        ? `Document Service ${res.status}: ${text.slice(0, 200)}`
        : `Document Service ${res.status}`,
    );
  }

  if (res.status === 204) {
    return { data: undefined, status: 204, headers: responseHeaders } as T;
  }

  const data = ct.includes('text/plain') ? await res.text() : await res.json();

  return {
    data,
    status: res.status,
    headers: responseHeaders,
  } as T;
};
