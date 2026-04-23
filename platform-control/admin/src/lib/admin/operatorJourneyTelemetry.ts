export type OperatorJourneyEventName =
  | "preflight_blocked"
  | "preflight_ready"
  | "preflight_retry"
  | "pipeline_health_loaded"
  | "remediation_action_clicked"
  | "legal_search_verification_opened";

export type OperatorJourneyEvent = {
  event: OperatorJourneyEventName;
  occurred_at: string;
  run_id?: string;
  source_id?: string;
  source_version_id?: string;
  mode?: "preview" | "production";
  readiness_codes?: string[];
  duration_ms?: number;
  stage?: "acquisition" | "document_intelligence" | "projection" | "search";
  action_label?: string;
  action_href?: string;
  previous_error_message?: string | null;
};

declare global {
  interface Window {
    __EVIDARA_OPERATOR_JOURNEY_EVENTS__?: OperatorJourneyEvent[];
  }
}

export function createOperatorJourneyEvent(
  event: OperatorJourneyEventName,
  payload: Omit<OperatorJourneyEvent, "event" | "occurred_at">,
): OperatorJourneyEvent {
  return {
    event,
    occurred_at: new Date().toISOString(),
    ...payload,
  };
}

export function emitOperatorJourneyEvent(
  event: OperatorJourneyEventName,
  payload: Omit<OperatorJourneyEvent, "event" | "occurred_at">,
): OperatorJourneyEvent {
  const data = createOperatorJourneyEvent(event, payload);
  if (typeof window !== "undefined") {
    window.__EVIDARA_OPERATOR_JOURNEY_EVENTS__ = window.__EVIDARA_OPERATOR_JOURNEY_EVENTS__ ?? [];
    window.__EVIDARA_OPERATOR_JOURNEY_EVENTS__.push(data);
  }
  // Structured logs are useful for local debugging and CI traceability.
  console.info("[operator-journey]", JSON.stringify(data));
  return data;
}
