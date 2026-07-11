"use client";

import { RefreshCw } from "lucide-react";
import {
  type ChangeEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { useDataProvider, useGetList, useNotify, useRedirect } from "react-admin";
import { ResourceName } from "../../domain/resourceNames";
import type {
  RunCreateInput,
  RunReadiness,
  RunRecord,
  SourceRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { emitOperatorJourneyEvent } from "../../lib/admin/operatorJourneyTelemetry";
import { describeReadinessDetail } from "../../lib/admin/readiness-messages";
import { Button, Dialog, FormField, InlineAlert, Panel, Pill } from "../../ui/primitives";
import { ConfirmButton } from "../shared/ConfirmButton";
import { runModeToLevel } from "../shared/statusLevels";

const LIST_PARAMS = {
  pagination: { page: 1, perPage: 250 },
  sort: { field: "name", order: "ASC" as const },
};

// Native <select> styled to match the ra-core `Select` primitive's trigger.
// The launch dialog holds its inputs in local state (not a ra-core `<Form>`),
// so the `useInput`-bound `Select` primitive can't be used here.
const NATIVE_SELECT_CLASS =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--surface-input)] " +
  "px-3 py-2.5 text-sm text-[var(--foreground)] shadow-[var(--shadow-inset-surface)] " +
  "transition-[border-color,box-shadow] hover:border-[var(--accent-core)]/30 " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

function LaunchSelect({
  label,
  value,
  onChange,
  disabled,
  helperText,
  children,
}: {
  label: string;
  value: string;
  onChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  disabled?: boolean;
  helperText?: ReactNode;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <FormField id={id} label={label} helperText={helperText}>
      <select
        id={id}
        value={value}
        onChange={onChange}
        disabled={disabled}
        className={NATIVE_SELECT_CLASS}
      >
        {children}
      </select>
    </FormField>
  );
}

type RunLaunchRedirectResource = typeof ResourceName.Runs | typeof ResourceName.PreviewReview;

type RunLaunchButtonProps = {
  label: string;
  buttonVariant?: "contained" | "outlined" | "text";
  buttonColor?: "primary" | "secondary";
  defaultMode?: "preview" | "production";
  allowedModes?: Array<"preview" | "production">;
  redirectResource?: RunLaunchRedirectResource;
};

type RunLaunchFormState = {
  source_id: string;
  source_version_id: string;
  mode: "preview" | "production";
};

const resolveInitialMode = (
  defaultMode: "preview" | "production",
  allowedModes: Array<"preview" | "production">,
): "preview" | "production" => {
  if (allowedModes.includes(defaultMode)) {
    return defaultMode;
  }
  return allowedModes[0] ?? "preview";
};

const createInitialState = (defaultMode: "preview" | "production"): RunLaunchFormState => ({
  source_id: "",
  source_version_id: "",
  mode: defaultMode,
});

const versionAllowedForMode = (
  status: SourceVersionRecord["status"],
  mode: "preview" | "production",
): boolean => {
  if (mode === "production") {
    return status === "approved";
  }
  return status !== "rejected" && status !== "superseded";
};

const RUN_READINESS_CONFIRMED_KEY_PREFIX = "evidara_run_readiness_confirmed:";
const RUN_READINESS_BLOCKED_CODES_KEY_PREFIX = "evidara_run_readiness_blocked_codes:";

const normalizeReadinessCodes = (checks: RunReadiness["checks"]): string[] =>
  Array.from(new Set(checks.filter((check) => !check.ok).map((check) => check.code))).sort();

const formatModeLabel = (mode: "preview" | "production"): string =>
  mode === "production" ? "Production" : "Preview";

export type PreflightRetryPayload = {
  source_id: string;
  source_version_id: string;
  mode: "preview" | "production";
  previous_error_message: string | null;
};

export function buildPreflightRetryPayload(
  formState: { source_id: string; source_version_id: string; mode: "preview" | "production" },
  readinessError: string | null,
): PreflightRetryPayload {
  return {
    source_id: formState.source_id,
    source_version_id: formState.source_version_id,
    mode: formState.mode,
    previous_error_message: readinessError ?? null,
  };
}

export function RunLaunchButton({
  label,
  buttonVariant = "contained",
  buttonColor = "primary",
  defaultMode = "production",
  allowedModes = ["preview", "production"],
  redirectResource = ResourceName.Runs,
}: RunLaunchButtonProps) {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const redirect = useRedirect();

  const [open, setOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCheckingReadiness, setIsCheckingReadiness] = useState(false);
  const [readiness, setReadiness] = useState<RunReadiness | null>(null);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const initialMode = resolveInitialMode(defaultMode, allowedModes);
  const [formState, setFormState] = useState<RunLaunchFormState>(createInitialState(initialMode));
  const readinessCheckStartedAtRef = useRef<number | null>(null);

  const sources = useGetList<SourceRecord>(ResourceName.Sources, {
    ...LIST_PARAMS,
    filter: {},
  });

  const sourceVersions = useGetList<SourceVersionRecord>("source-versions", {
    pagination: { page: 1, perPage: 100 },
    sort: { field: "created_at", order: "DESC" as const },
    filter: { source_id: formState.source_id || "__none__" },
  });
  const selectedSource = useMemo(
    () => (sources.data ?? []).find((source) => source.source_id === formState.source_id) ?? null,
    [formState.source_id, sources.data],
  );
  const selectedVersion = useMemo(
    () =>
      (sourceVersions.data ?? []).find(
        (version) => version.source_version_id === formState.source_version_id,
      ) ?? null,
    [formState.source_version_id, sourceVersions.data],
  );

  const versionChoices = useMemo(() => {
    const versions = sourceVersions.data ?? [];
    return versions
      .filter((version) => versionAllowedForMode(version.status, formState.mode))
      .map((version) => ({
        value: version.source_version_id,
        label: `${version.version_label} (${version.status})`,
      }));
  }, [sourceVersions.data, formState.mode]);

  useEffect(() => {
    const versions = sourceVersions.data ?? [];
    const allowedIds = new Set(
      versions
        .filter((v) => versionAllowedForMode(v.status, formState.mode))
        .map((v) => v.source_version_id),
    );
    if (formState.source_version_id && !allowedIds.has(formState.source_version_id)) {
      setFormState((prev) => ({ ...prev, source_version_id: "" }));
    }
  }, [formState.mode, formState.source_version_id, sourceVersions.data]);

  const reset = () => {
    setFormState(createInitialState(initialMode));
    setReadiness(null);
    setReadinessError(null);
  };

  const closeDialog = () => {
    if (isSubmitting) {
      return;
    }
    setOpen(false);
    reset();
  };

  const submit = async () => {
    try {
      setIsSubmitting(true);
      const result = await dataProvider.create<RunRecord>(ResourceName.Runs, {
        data: formState as RunCreateInput,
      });
      if (typeof window !== "undefined") {
        const runId = String(result.data.run_id);
        window.localStorage.setItem(`${RUN_READINESS_CONFIRMED_KEY_PREFIX}${runId}`, "true");
        window.localStorage.removeItem(`${RUN_READINESS_BLOCKED_CODES_KEY_PREFIX}${runId}`);
      }
      notify(`${formState.mode === "preview" ? "Preview" : "Production"} run created.`, {
        type: "success",
      });
      setOpen(false);
      reset();
      redirect("show", redirectResource, result.data.id, result.data);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to create run.", {
        type: "error",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const runPreflight = useCallback(
    (input: RunLaunchFormState, isActive: () => boolean = () => true) => {
      const canCheck = Boolean(input.source_id && input.source_version_id);
      if (!canCheck) {
        setReadiness(null);
        setReadinessError(null);
        setIsCheckingReadiness(false);
        return;
      }

      setIsCheckingReadiness(true);
      setReadinessError(null);
      readinessCheckStartedAtRef.current = Date.now();

      void controlPlaneActions
        .getRunReadiness(input)
        .then((result) => {
          if (!isActive()) return;
          setReadiness(result);
          const elapsedMs =
            readinessCheckStartedAtRef.current != null
              ? Date.now() - readinessCheckStartedAtRef.current
              : undefined;
          if (result.ready) {
            emitOperatorJourneyEvent("preflight_ready", {
              source_id: input.source_id,
              source_version_id: input.source_version_id,
              mode: input.mode,
              readiness_codes: [],
              duration_ms: elapsedMs,
            });
          } else {
            const readinessCodes = normalizeReadinessCodes(result.checks);
            emitOperatorJourneyEvent("preflight_blocked", {
              source_id: input.source_id,
              source_version_id: input.source_version_id,
              mode: input.mode,
              readiness_codes: readinessCodes,
              duration_ms: elapsedMs,
            });
          }
        })
        .catch((error: unknown) => {
          if (!isActive()) return;
          setReadiness(null);
          setReadinessError(
            error instanceof Error ? error.message : "Unable to run preflight checks.",
          );
        })
        .finally(() => {
          if (!isActive()) return;
          setIsCheckingReadiness(false);
        });
    },
    [],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: retryNonce bumps deliberately retrigger the effect so the retry runs under the same formState-scoped `active` guard as the initial check.
  useEffect(() => {
    let active = true;
    runPreflight(formState, () => active);
    return () => {
      active = false;
    };
  }, [formState, runPreflight, retryNonce]);

  const handleRetry = () => {
    const previousError = readinessError;
    setReadiness(null);
    setReadinessError(null);
    emitOperatorJourneyEvent(
      "preflight_retry",
      buildPreflightRetryPayload(formState, previousError),
    );
    // Re-run preflight via the effect so it inherits the formState-scoped
    // `active` guard — a direct call here would race with subsequent
    // source/version edits and overwrite readiness for a stale pair.
    setRetryNonce((n) => n + 1);
  };

  const failingChecks = useMemo(
    () => readiness?.checks.filter((check) => !check.ok) ?? [],
    [readiness],
  );
  const readinessStatusLabel = isCheckingReadiness
    ? "Preflight checking"
    : readinessError
      ? "Preflight error"
      : readiness?.ready
        ? "Preflight ready"
        : readiness
          ? "Preflight blocked"
          : "Preflight pending";
  const isReadyToCreate =
    !!formState.source_id &&
    !!formState.source_version_id &&
    !isSubmitting &&
    !isCheckingReadiness &&
    !readinessError &&
    !!readiness?.ready;
  const triggerVariant =
    buttonVariant === "text"
      ? "ghost"
      : buttonVariant === "outlined" || buttonColor === "secondary"
        ? "secondary"
        : "primary";

  const footer = (
    <>
      <Button variant="secondary" onClick={closeDialog} disabled={isSubmitting}>
        Cancel
      </Button>
      {formState.mode === "production" ? (
        <ConfirmButton
          tier="notable"
          variant="contained"
          color="success"
          disabled={!isReadyToCreate || isSubmitting}
          confirmTitle="Create production run?"
          confirmDescription="Production runs schedule real pipeline work against the selected approved version. Confirm only when you intend to verify capture end-to-end."
          confirmLabel="Create run"
          cancelLabel="Go back"
          onConfirm={submit}
        >
          {isSubmitting ? "Creating..." : "Create Run"}
        </ConfirmButton>
      ) : (
        <Button variant="primary" onClick={submit} disabled={!isReadyToCreate}>
          {isSubmitting ? "Creating..." : "Create Run"}
        </Button>
      )}
    </>
  );

  return (
    <>
      <Button variant={triggerVariant} onClick={() => setOpen(true)}>
        {label}
      </Button>

      <Dialog
        open={open}
        onClose={closeDialog}
        title="Create Run"
        description="Pick a source/version pair, then review the preflight result before launch."
        size="md"
        dismissable={!isSubmitting}
        footer={footer}
      >
        <div className="flex flex-col gap-4">
          {sources.error ? <InlineAlert tone="error">Unable to load sources.</InlineAlert> : null}

          <Panel className="p-4">
            <div className="flex flex-col gap-3">
              <p className="text-sm font-semibold text-[var(--foreground)] m-0">Launch summary</p>
              <div className="flex flex-wrap gap-2">
                <Pill level={runModeToLevel(formState.mode)}>
                  {`${formatModeLabel(formState.mode)} mode`}
                </Pill>
                <Pill variant="meta">{`Source ${selectedSource?.name ?? "not selected"}`}</Pill>
                <Pill variant="meta">
                  {selectedVersion
                    ? `Version ${selectedVersion.version_label} (${selectedVersion.status})`
                    : "Version not selected"}
                </Pill>
                <Pill variant="meta">{readinessStatusLabel}</Pill>
              </div>
              <p className="text-sm text-[var(--text-meta)] m-0">
                {formState.mode === "production"
                  ? "Production runs require an approved version and should be used when the source is ready for operator verification."
                  : "Preview runs let you inspect capture quality and readiness before promotion."}
              </p>
            </div>
          </Panel>

          <Panel className="p-4">
            <div className="flex flex-col gap-4">
              <p className="text-sm font-semibold text-[var(--foreground)] m-0">Launch inputs</p>

              <LaunchSelect
                label="Run mode"
                value={formState.mode}
                disabled={allowedModes.length === 1}
                onChange={(event) => {
                  const mode = event.target.value as RunLaunchFormState["mode"];
                  setFormState((prev) => {
                    const versions = sourceVersions.data ?? [];
                    const allowedIds = new Set(
                      versions
                        .filter((v) => versionAllowedForMode(v.status, mode))
                        .map((v) => v.source_version_id),
                    );
                    return {
                      ...prev,
                      mode,
                      source_version_id: allowedIds.has(prev.source_version_id)
                        ? prev.source_version_id
                        : "",
                    };
                  });
                }}
              >
                {allowedModes.map((mode) => (
                  <option key={mode} value={mode}>
                    {formatModeLabel(mode)}
                  </option>
                ))}
              </LaunchSelect>

              <LaunchSelect
                label="Source"
                value={formState.source_id}
                onChange={(event) =>
                  setFormState({
                    ...formState,
                    source_id: event.target.value,
                    source_version_id: "",
                  })
                }
              >
                <option value="">Select a source…</option>
                {(sources.data ?? []).map((source) => (
                  <option key={source.source_id} value={source.source_id}>
                    {source.name}
                  </option>
                ))}
              </LaunchSelect>

              <LaunchSelect
                label="Source version"
                value={formState.source_version_id}
                disabled={!formState.source_id}
                helperText="Production runs require an approved version."
                onChange={(event) =>
                  setFormState({
                    ...formState,
                    source_version_id: event.target.value,
                  })
                }
              >
                <option value="">Select a version…</option>
                {versionChoices.map((version) => (
                  <option key={version.value} value={version.value}>
                    {version.label}
                  </option>
                ))}
              </LaunchSelect>
            </div>
          </Panel>

          {isCheckingReadiness ? (
            <InlineAlert tone="info">
              <p className="font-semibold text-[var(--foreground)]">Checking preflight readiness</p>
              <p>The launch dialog is validating the selected source/version pair.</p>
            </InlineAlert>
          ) : null}
          {readinessError ? (
            <InlineAlert tone="error">
              <div className="flex items-start justify-between gap-3">
                <span>{readinessError}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleRetry}
                  disabled={isCheckingReadiness}
                  leftIcon={<RefreshCw size={14} />}
                >
                  Retry
                </Button>
              </div>
            </InlineAlert>
          ) : null}
          {readiness && !readiness.ready ? (
            <InlineAlert tone="warning">
              <div className="flex flex-col gap-3">
                <p className="font-semibold text-[var(--foreground)]">Preflight blocks launch</p>
                <p className="font-semibold text-[var(--foreground)]">
                  Preflight is blocking launch. Resolve the items below to enable Create Run.
                </p>
                <div className="flex flex-col gap-2">
                  {failingChecks.map((check) => {
                    const info = describeReadinessDetail(check.code);
                    return (
                      <Panel key={check.code} className="p-3">
                        <div className="flex flex-col gap-1">
                          <p className="text-sm font-semibold text-[var(--foreground)] m-0">
                            {info.title}
                          </p>
                          <p className="text-sm text-[var(--text-meta)] m-0">{check.detail}</p>
                          <p className="text-xs text-[var(--text-meta)] m-0">
                            Next action: {info.action}
                          </p>
                        </div>
                      </Panel>
                    );
                  })}
                </div>
                <p className="text-xs text-[var(--foreground)] m-0">
                  {failingChecks.length} blocked check
                  {failingChecks.length === 1 ? "" : "s"} need attention before the run can be
                  created.
                </p>
                {selectedVersion ? (
                  <p className="text-xs text-[var(--foreground)] m-0">
                    Selected version status: {selectedVersion.status}
                  </p>
                ) : null}
              </div>
            </InlineAlert>
          ) : null}
          {readiness?.ready ? (
            <InlineAlert tone="success">
              <p className="font-semibold text-[var(--foreground)]">Preflight ready</p>
              <p>The current source/version pair is ready to launch.</p>
            </InlineAlert>
          ) : null}
        </div>
      </Dialog>
    </>
  );
}
