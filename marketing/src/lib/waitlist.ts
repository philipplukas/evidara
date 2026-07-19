/**
 * Waitlist submission — the seam between the page and whatever eventually
 * stores an address.
 *
 * ── Why there is no backend behind this yet (ADR-0039) ──
 *
 * Deliberate. The page ships before the store does, for two reasons:
 *
 *  1. A public, unauthenticated write endpoint does NOT belong in
 *     platform-control. That service is the operator control plane — source
 *     lifecycle, approvals, compliance policies — and #680 just made it fail
 *     closed on purpose. Bolting a public write path onto it would hand the
 *     least-trusted surface in the system a network route into the most
 *     privileged one, sharing a process, a connection pool and a database
 *     role with approvals. The isolation is worth more than the convenience.
 *
 *  2. Collecting an email address in the EU is not a `INSERT INTO`. It is
 *     consent capture, double opt-in, unsubscribe, bounce handling, and an
 *     erasure path. That is the actual work, and it is work Listmonk has
 *     already done.
 *
 * So the seam is a single function with a configured-or-not contract. Point
 * `NEXT_PUBLIC_WAITLIST_ENDPOINT` at a Listmonk `/api/public/subscription`
 * (or anything else that accepts a JSON POST) and the form starts working —
 * no component changes, no rewrite. Until then the UI tells the truth:
 * signups are not open yet.
 *
 * The endpoint is read at BUILD time because this surface is statically
 * exported (`output: "export"`); there is no server to read it at runtime.
 */

/** Field the honeypot lives in. Bots fill it; humans never see it. */
export const HONEYPOT_FIELD = "company_website";

export type WaitlistResult =
  /** The store is configured and accepted the address. */
  | { status: "ok" }
  /** No store is configured yet — the UI must say so rather than pretend. */
  | { status: "not-configured" }
  /** Honeypot tripped. Reported as success so a bot learns nothing. */
  | { status: "rejected" }
  /** The store is configured but the request failed. */
  | { status: "error"; message: string };

export interface WaitlistSubmission {
  email: string;
  /** Optional free-text context. Never required. */
  role?: string;
  /** Honeypot value. Non-empty means "not a human". */
  honeypot?: string;
}

/** RFC-5322-lite. Good enough for a client-side hint; the store re-validates. */
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim());
}

export function getWaitlistEndpoint(): string | undefined {
  const configured = process.env.NEXT_PUBLIC_WAITLIST_ENDPOINT?.trim();
  return configured ? configured : undefined;
}

export async function submitWaitlist(
  submission: WaitlistSubmission,
  // Injected for tests; defaults to the platform fetch.
  fetchImpl: typeof fetch = globalThis.fetch,
): Promise<WaitlistResult> {
  // Honeypot first — before any network call, so a bot costs us nothing.
  if (submission.honeypot && submission.honeypot.trim() !== "") {
    return { status: "rejected" };
  }

  const endpoint = getWaitlistEndpoint();
  if (!endpoint) {
    return { status: "not-configured" };
  }

  try {
    const response = await fetchImpl(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: submission.email.trim(),
        role: submission.role?.trim() || undefined,
      }),
    });

    if (!response.ok) {
      // Duplicate submission is NOT an error the visitor should see. A store
      // that reports "already subscribed" as 409 must read as success here:
      // telling a stranger whether an address is already on the list is an
      // address-enumeration oracle, and it is a confusing thing to show
      // someone who simply submitted twice.
      if (response.status === 409) {
        return { status: "ok" };
      }
      return { status: "error", message: `Request failed (${response.status}).` };
    }

    return { status: "ok" };
  } catch {
    return { status: "error", message: "Could not reach the server." };
  }
}
