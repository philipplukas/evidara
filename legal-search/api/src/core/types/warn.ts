/**
 * Observable warning function type for mapper fallbacks.
 *
 * Mappers accept an optional warn function to report unknown vocabulary
 * values, missing fields, and other contract violations without crashing.
 *
 * ADR-0012: "Unknown controlled vocabulary values are invalid at the
 * producer contract level, but downstream consumers must degrade safely
 * and emit telemetry rather than silently masking the issue."
 */
export type WarnFn = (event: string, meta: Record<string, unknown>) => void;

/** No-op warn — used when no telemetry is needed (e.g., in tests). */
export const noopWarn: WarnFn = () => {};
