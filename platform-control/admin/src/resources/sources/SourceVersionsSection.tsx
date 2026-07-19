/**
 * `SourceVersionsSection` — Tailwind + ra-core source-version lifecycle
 * surface, rendered inside the source-detail page (`SourceShow`). It owns:
 *
 *   - a lifecycle rollup (counts + next-operator-action) built from the
 *     `summarizeSourceVersionLifecycle` helper;
 *   - a version table with edit / compare / preview-run / production-run /
 *     approve / reject affordances (the mutating ones gated behind a
 *     confirm dialog);
 *   - the create / edit form dialog, whose provider-specific fields turn
 *     into an `acquisition_spec` via the `toAcquisitionSpec` helper.
 *
 * All pure form + lifecycle logic lives in `./sourceVersionForm`; the diff
 * view reuses `SourceVersionDiffPanel`. No MUI imports (ADR-0026).
 */
"use client";

import { ChevronDown } from "lucide-react";
import { useDataProvider, useGetList, useNotify, useRedirect, useRefresh } from "ra-core";
import { Fragment, type ReactNode, useEffect, useId, useMemo, useState } from "react";
import { ResourceName } from "../../domain/resourceNames";
import type {
  RunReadiness,
  RunRecord,
  SourceRecord,
  SourceVersionRecord,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import {
  Button,
  Checkbox,
  cn,
  Dialog,
  FormField,
  InlineAlert,
  Panel,
  Pill,
} from "../../ui/primitives";
import { sourceVersionStatusToLevel } from "../shared/statusLevels";
import { SourceVersionDiffPanel } from "./SourceVersionDiffPanel";
import {
  describeSourceVersionStatus,
  emptyFormState,
  explainUnavailableVersionAction,
  OVERLAY_CHOICES,
  PROVIDER_CHOICES,
  PROVIDER_TEMPLATE_CHOICES,
  type ProviderType,
  SOURCE_VERSION_LIST_PARAMS,
  type SourceVersionAction,
  type SourceVersionFormState,
  summarizeAcquisitionSpec,
  summarizeSourceVersionLifecycle,
  toAcquisitionSpec,
  toFormState,
} from "./sourceVersionForm";
import {
  deriveVersionLaunchGuards,
  describeLaunchBlockRollup,
  type LaunchGuard,
  type VersionLaunchGuards,
} from "./sourceVersionLaunch";

const INPUT_CLASS =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--surface-input)] px-3 py-2.5 text-sm text-[var(--foreground)] " +
  "placeholder:text-[var(--foreground-subtle)] shadow-[var(--shadow-inset-surface)] " +
  "transition-[border-color,box-shadow] hover:border-[var(--accent-core)]/30 " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const DANGER_BUTTON =
  "bg-[var(--status-critical)] text-[var(--accent-core-foreground)] border-transparent " +
  "hover:bg-[color-mix(in_oklab,var(--status-critical)_88%,black)] shadow-[var(--shadow-card)]";

/** Label + native text/number input row for the local-state dialog form. */
function TextRow({
  label,
  value,
  onChange,
  helperText,
  placeholder,
  multiline,
  rows = 2,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  helperText?: ReactNode;
  placeholder?: string;
  multiline?: boolean;
  rows?: number;
  type?: "text" | "number";
}) {
  const id = useId();
  return (
    <FormField id={id} label={label} helperText={helperText}>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          rows={rows}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          className={cn(INPUT_CLASS, "resize-y leading-snug")}
        />
      ) : (
        <input
          id={id}
          type={type}
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          className={INPUT_CLASS}
        />
      )}
    </FormField>
  );
}

/** Label + native `<select>` row (chevron overlay, token styling). */
function SelectRow({
  label,
  value,
  onChange,
  children,
  helperText,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  children: ReactNode;
  helperText?: ReactNode;
}) {
  const id = useId();
  return (
    <FormField id={id} label={label} helperText={helperText}>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={cn(INPUT_CLASS, "appearance-none pr-9")}
        >
          {children}
        </select>
        <ChevronDown
          size={16}
          aria-hidden
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--foreground-subtle)]"
        />
      </div>
    </FormField>
  );
}

/** Provider-specific form body shared by the create + edit dialog. */
function SourceVersionForm({
  formState,
  onChange,
}: {
  formState: SourceVersionFormState;
  onChange: (next: SourceVersionFormState) => void;
}) {
  return (
    <div className="space-y-4">
      <TextRow
        label="Version label"
        value={formState.version_label}
        onChange={(version_label) => onChange({ ...formState, version_label })}
      />
      <TextRow
        label="Extractor profile ID"
        value={formState.extractor_profile_id}
        onChange={(extractor_profile_id) => onChange({ ...formState, extractor_profile_id })}
      />
      <Checkbox
        label="Use country overlay + provider template"
        checked={formState.use_blueprint}
        onCheckedChange={(use_blueprint) => onChange({ ...formState, use_blueprint })}
      />

      {formState.use_blueprint ? (
        <>
          <SelectRow
            label="Country overlay"
            value={formState.overlay_id}
            onChange={(overlay_id) =>
              onChange({
                ...formState,
                overlay_id,
                provider_template_id: PROVIDER_TEMPLATE_CHOICES[overlay_id]?.[0]?.value ?? "",
              })
            }
          >
            {OVERLAY_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </SelectRow>
          <SelectRow
            label="Provider template"
            value={formState.provider_template_id}
            onChange={(provider_template_id) => onChange({ ...formState, provider_template_id })}
          >
            {(PROVIDER_TEMPLATE_CHOICES[formState.overlay_id] ?? []).map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </SelectRow>
          <InlineAlert tone="info">
            Wizard preview: source version will be created from overlay{" "}
            <strong>{formState.overlay_id}</strong> and template{" "}
            <strong>{formState.provider_template_id || "not selected"}</strong>.
          </InlineAlert>
        </>
      ) : !formState.spec_editable ? (
        <>
          <InlineAlert tone="warning">
            <div className="space-y-1">
              <p className="font-semibold text-[var(--foreground)]">
                This acquisition spec is read-only.
              </p>
              <p className="text-[var(--foreground-muted)]">
                Provider <strong>{formState.original_spec?.provider}</strong> has no editor here, so
                its spec is shown as-is and saved back unchanged — the version label and extractor
                profile above are still editable. To replace the spec, tick “Use country overlay +
                provider template”.
              </p>
            </div>
          </InlineAlert>
          <pre className="m-0 max-h-64 overflow-auto rounded-md border border-[var(--border-faint)] bg-[var(--surface-input)] p-3 font-mono text-[11px] leading-[1.6] text-[var(--foreground-muted)]">
            {JSON.stringify(formState.original_spec, null, 2)}
          </pre>
        </>
      ) : (
        <>
          <p className="text-[13px] text-[var(--foreground-subtle)]">
            Manual mode: provider-specific fields are sent directly as acquisition_spec.
          </p>
          <SelectRow
            label="Provider"
            value={formState.provider}
            onChange={(provider) => onChange({ ...formState, provider: provider as ProviderType })}
          >
            {PROVIDER_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </SelectRow>

          {formState.provider === "ris_ogd" ? (
            <>
              <TextRow
                label="Base URL"
                value={formState.base_url}
                onChange={(base_url) => onChange({ ...formState, base_url })}
                helperText="OGD-RIS API endpoint, e.g. https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"
              />
              <TextRow
                label="Applikation"
                value={formState.applikation}
                onChange={(applikation) => onChange({ ...formState, applikation })}
                helperText="Optional filter: Vfgh, Vwgh, Bvwg, Justiz, BrKons, BgblAuth"
              />
              <TextRow
                label="Preferred formats"
                value={formState.preferred_formats_text}
                onChange={(preferred_formats_text) =>
                  onChange({ ...formState, preferred_formats_text })
                }
                helperText="Comma separated. E.g. Xml, Html"
              />
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <TextRow
                  label="Page size"
                  type="number"
                  value={formState.page_size}
                  onChange={(page_size) => onChange({ ...formState, page_size })}
                />
                <TextRow
                  label="Max pages"
                  type="number"
                  value={formState.max_pages}
                  onChange={(max_pages) => onChange({ ...formState, max_pages })}
                />
              </div>
            </>
          ) : formState.provider === "fedlex_sparql" ? (
            <>
              <TextRow
                label="Seed work URI"
                value={formState.seed_url}
                onChange={(seed_url) => onChange({ ...formState, seed_url })}
                helperText="Canonical Fedlex work URI, e.g. https://fedlex.data.admin.ch/eli/cc/1999/404"
              />
              <TextRow
                label="Additional seed work URIs"
                multiline
                value={formState.seed_urls_text}
                onChange={(seed_urls_text) => onChange({ ...formState, seed_urls_text })}
                helperText="Optional comma or newline separated additional Fedlex work URIs."
              />
              <TextRow
                label="SPARQL endpoint"
                value={formState.sparql_endpoint}
                onChange={(sparql_endpoint) => onChange({ ...formState, sparql_endpoint })}
                helperText="Defaults to the public Fedlex SPARQL endpoint."
              />
              <TextRow
                label="Preferred languages"
                value={formState.preferred_languages_text}
                onChange={(preferred_languages_text) =>
                  onChange({ ...formState, preferred_languages_text })
                }
                helperText="Comma or newline separated language codes."
              />
              <SelectRow
                label="Query mode"
                value={formState.query_mode}
                onChange={(query_mode) =>
                  onChange({
                    ...formState,
                    query_mode: query_mode as SourceVersionFormState["query_mode"],
                  })
                }
              >
                <option value="work_to_expression">work_to_expression</option>
              </SelectRow>
              <TextRow
                label="Max expressions"
                type="number"
                value={formState.max_expressions}
                onChange={(max_expressions) => onChange({ ...formState, max_expressions })}
                helperText="How many expressions to resolve per work URI."
              />
            </>
          ) : (
            <>
              <TextRow
                label="Seed URL"
                value={formState.seed_url}
                onChange={(seed_url) => onChange({ ...formState, seed_url })}
              />
              <TextRow
                label="Additional seed URLs"
                multiline
                value={formState.seed_urls_text}
                onChange={(seed_urls_text) => onChange({ ...formState, seed_urls_text })}
                helperText="Comma or newline separated."
              />
              <SelectRow
                label="Mode"
                value={formState.mode}
                onChange={(mode) =>
                  onChange({ ...formState, mode: mode as SourceVersionFormState["mode"] })
                }
              >
                <option value="crawl">crawl</option>
                <option value="batch_scrape">batch_scrape</option>
              </SelectRow>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <TextRow
                  label="Limit"
                  type="number"
                  value={formState.limit}
                  onChange={(limit) => onChange({ ...formState, limit })}
                />
                <TextRow
                  label="Max discovery depth"
                  type="number"
                  value={formState.max_discovery_depth}
                  onChange={(max_discovery_depth) =>
                    onChange({ ...formState, max_discovery_depth })
                  }
                />
              </div>
              <TextRow
                label="Include paths"
                multiline
                value={formState.include_paths_text}
                onChange={(include_paths_text) => onChange({ ...formState, include_paths_text })}
                helperText="Comma or newline separated."
              />
              <TextRow
                label="Exclude paths"
                multiline
                value={formState.exclude_paths_text}
                onChange={(exclude_paths_text) => onChange({ ...formState, exclude_paths_text })}
                helperText="Comma or newline separated."
              />
              <TextRow
                label="Scrape formats"
                value={formState.scrape_formats_text}
                onChange={(scrape_formats_text) => onChange({ ...formState, scrape_formats_text })}
                helperText="Comma or newline separated."
              />
              <Checkbox
                label="Zero data retention"
                checked={formState.zero_data_retention}
                onCheckedChange={(zero_data_retention) =>
                  onChange({ ...formState, zero_data_retention })
                }
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

type ConfirmKind = "approve" | "reject" | "production";

type ConfirmState = {
  kind: ConfirmKind;
  version: SourceVersionRecord;
};

const CONFIRM_COPY: Record<
  ConfirmKind,
  { title: string; describe: (label: string) => string; confirmLabel: string; danger: boolean }
> = {
  production: {
    title: "Launch production run?",
    describe: (label) =>
      `This will start a production pipeline for ${label}. Production runs create real artifacts.`,
    confirmLabel: "Launch production",
    danger: false,
  },
  approve: {
    title: "Approve this version?",
    describe: (label) =>
      `Approving ${label} makes it eligible for production runs. Ensure the version has been reviewed.`,
    confirmLabel: "Approve",
    danger: false,
  },
  reject: {
    title: "Reject this version?",
    describe: (label) =>
      `Rejecting ${label} will permanently block it from production use. This cannot be undone.`,
    confirmLabel: "Reject version",
    danger: true,
  },
};

/**
 * A lifecycle action on one version, which states *why* it is unavailable.
 *
 * A greyed button is not an explanation (#674). When the action is blocked by
 * the version's status, the reason becomes both a native tooltip (`title`) and
 * an accessible description, so the rule — "approval is terminal", "production
 * runs require an approved version" — is readable rather than inferred.
 *
 * `busy` (an in-flight request on this row) also disables the button, but is
 * transient and self-evident, so it carries no explanation.
 *
 * For the two launch actions a `guard` from `/v1/runs/readiness` supersedes the
 * status-only rule (#667): status alone cannot see an inert blueprint template,
 * and `deriveVersionLaunchGuards` already folds the status reason in, so the
 * guard is strictly the better-informed answer. It also carries the two
 * "I don't know" states — `checking` (disabled) and `unknown` (enabled, but the
 * reason says the check did not complete) — which a status rule cannot express.
 */
function VersionActionButton({
  action,
  status,
  busy,
  versionId,
  variant = "secondary",
  className,
  onClick,
  children,
  guard = null,
}: {
  action: SourceVersionAction;
  status: SourceVersionRecord["status"];
  busy: boolean;
  versionId: string;
  variant?: "primary" | "secondary" | "ghost";
  className?: string;
  onClick: () => void;
  children: ReactNode;
  guard?: LaunchGuard | null;
}) {
  const reason = guard ? guard.reason : explainUnavailableVersionAction(action, status);
  const blocked = guard ? !guard.allowed : reason !== null;
  const describedById = reason ? `version-action-${versionId}-${action}` : undefined;

  return (
    <>
      <Button
        size="sm"
        variant={variant}
        className={className}
        onClick={onClick}
        disabled={blocked || busy}
        title={reason ?? undefined}
        aria-describedby={describedById}
      >
        {children}
      </Button>
      {reason ? (
        <span id={describedById} className="sr-only">
          {reason}
        </span>
      ) : null}
    </>
  );
}

type ReadinessEntry = { readiness: RunReadiness | null; error: string | null };

/**
 * Probe `/v1/runs/readiness` once per version so the launch buttons on this page
 * are gated by the same pre-flight `POST /v1/runs` enforces (#667).
 *
 * `mode: "production"` is the strictest probe and its non-mode checks — the
 * ADR-0030 two-key lock in particular — apply to preview runs identically;
 * `deriveVersionLaunchGuards` separates the one mode-dependent check back out.
 * A version list is per-source and small, so one request each is cheaper than
 * adding a bulk endpoint and keeps the authoritative answer authoritative.
 */
function useVersionLaunchReadiness(
  sourceId: string,
  versions: SourceVersionRecord[],
): Record<string, ReadinessEntry> {
  const [entries, setEntries] = useState<Record<string, ReadinessEntry>>({});
  // Re-probe only when the actual set of version ids changes, not on every
  // re-render of the (new-identity-each-time) array from `useGetList`.
  const versionKey = versions.map((version) => version.source_version_id).join(",");

  useEffect(() => {
    if (!sourceId || versionKey.length === 0) {
      setEntries({});
      return;
    }
    let active = true;
    // Clear first so rows report "checking" rather than reusing a stale verdict
    // from the previously selected source.
    setEntries({});

    const ids = versionKey.split(",");
    void Promise.all(
      ids.map(async (sourceVersionId): Promise<[string, ReadinessEntry]> => {
        try {
          const readiness = await controlPlaneActions.getRunReadiness({
            source_id: sourceId,
            source_version_id: sourceVersionId,
            mode: "production",
          });
          return [sourceVersionId, { readiness, error: null }];
        } catch (error) {
          return [
            sourceVersionId,
            {
              readiness: null,
              error: error instanceof Error ? error.message : "readiness check failed",
            },
          ];
        }
      }),
    ).then((results) => {
      if (!active) return;
      setEntries(Object.fromEntries(results));
    });

    return () => {
      active = false;
    };
  }, [sourceId, versionKey]);

  return entries;
}

export function SourceVersionsSection({ source }: { source: SourceRecord }) {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const redirect = useRedirect();
  const refresh = useRefresh();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVersion, setEditingVersion] = useState<SourceVersionRecord | null>(null);
  const [formState, setFormState] = useState<SourceVersionFormState>(emptyFormState());
  const [isSaving, setIsSaving] = useState(false);
  const [actionVersionId, setActionVersionId] = useState<string | null>(null);
  const [diffVersionId, setDiffVersionId] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);

  const versions = useGetList<SourceVersionRecord>("source-versions", {
    pagination: SOURCE_VERSION_LIST_PARAMS.pagination,
    sort: SOURCE_VERSION_LIST_PARAMS.sort,
    filter: { source_id: source.source_id },
  });

  const lifecycle = summarizeSourceVersionLifecycle(versions.data ?? []);

  const readinessEntries = useVersionLaunchReadiness(source.source_id, versions.data ?? []);

  const guardsByVersion = useMemo(() => {
    const map: Record<string, VersionLaunchGuards> = {};
    for (const version of versions.data ?? []) {
      const entry = readinessEntries[version.source_version_id];
      map[version.source_version_id] = deriveVersionLaunchGuards({
        status: version.status,
        readiness: entry?.readiness ?? null,
        readinessError: entry?.error ?? null,
      });
    }
    return map;
  }, [versions.data, readinessEntries]);

  // The rollup that replaces "Approved versions are ready for operator use and
  // run creation." whenever readiness disagrees with that claim (#667).
  const launchRollup = describeLaunchBlockRollup(Object.values(guardsByVersion));

  const attentionTone =
    lifecycle.total === 0
      ? "info"
      : launchRollup
        ? launchRollup.tone
        : lifecycle.attentionCount > 0
          ? "warning"
          : "success";
  const attentionLabel =
    lifecycle.total === 0
      ? "Awaiting first version"
      : launchRollup
        ? "Launch blocked"
        : lifecycle.attentionCount > 0
          ? `${lifecycle.attentionCount} need attention`
          : "No attention needed";

  const openCreateDialog = () => {
    setEditingVersion(null);
    setFormState(emptyFormState());
    setDialogOpen(true);
  };

  const openEditDialog = (version: SourceVersionRecord) => {
    setEditingVersion(version);
    setFormState(toFormState(version));
    setDialogOpen(true);
  };

  const closeDialog = () => {
    if (isSaving) {
      return;
    }
    setDialogOpen(false);
    setEditingVersion(null);
    setFormState(emptyFormState());
  };

  const submitDialog = async () => {
    try {
      setIsSaving(true);
      const payloadTail = formState.use_blueprint
        ? {
            overlay_id: formState.overlay_id,
            provider_template_id: formState.provider_template_id,
          }
        : { acquisition_spec: toAcquisitionSpec(formState) };

      if (editingVersion) {
        await dataProvider.update("source-versions", {
          id: editingVersion.source_version_id,
          data: {
            version_label: formState.version_label,
            extractor_profile_id: formState.extractor_profile_id,
            ...payloadTail,
          },
          previousData: editingVersion,
        });
        notify("Source version updated.", { type: "success" });
      } else {
        await dataProvider.create("source-versions", {
          data: {
            source_id: source.source_id,
            version_label: formState.version_label,
            extractor_profile_id: formState.extractor_profile_id,
            ...payloadTail,
          },
        });
        notify("Source version created.", { type: "success" });
      }
      setDialogOpen(false);
      setEditingVersion(null);
      setFormState(emptyFormState());
      refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to save source version.", {
        type: "error",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const runVersionAction = async (action: "approve" | "reject", version: SourceVersionRecord) => {
    try {
      setActionVersionId(version.source_version_id);
      if (action === "approve") {
        await controlPlaneActions.approveSourceVersion(version.source_version_id);
        notify("Source version approved.", { type: "success" });
      } else {
        await controlPlaneActions.rejectSourceVersion(version.source_version_id);
        notify("Source version rejected.", { type: "success" });
      }
      refresh();
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to update source version state.", {
        type: "error",
      });
    } finally {
      setActionVersionId(null);
    }
  };

  const createRun = async (mode: "preview" | "production", version: SourceVersionRecord) => {
    try {
      setActionVersionId(version.source_version_id);
      const result = await dataProvider.create<RunRecord>(ResourceName.Runs, {
        data: {
          source_id: source.source_id,
          source_version_id: version.source_version_id,
          mode,
        },
      });
      notify(`${mode === "preview" ? "Preview" : "Production"} run created.`, { type: "success" });
      redirect("show", ResourceName.Runs, result.data.id, result.data);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Unable to create run.", { type: "error" });
    } finally {
      setActionVersionId(null);
    }
  };

  const runConfirm = async () => {
    if (!confirm) {
      return;
    }
    const { kind, version } = confirm;
    setConfirm(null);
    if (kind === "production") {
      await createRun("production", version);
    } else {
      await runVersionAction(kind, version);
    }
  };

  const rows = versions.data ?? [];

  return (
    <Panel className="p-5 sm:p-6" testId="source-versions-section">
      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Source versions</h2>
            <p className="text-[13px] text-[var(--foreground-subtle)]">
              Create, review, and transition source versions for this source.
            </p>
          </div>
          <Button variant="primary" onClick={openCreateDialog}>
            Create version
          </Button>
        </div>

        {versions.error ? (
          <InlineAlert tone="error">Unable to load source versions.</InlineAlert>
        ) : null}

        {versions.isPending && !versions.error ? (
          <InlineAlert tone="info">Loading source versions…</InlineAlert>
        ) : null}

        {!versions.isPending && !versions.error ? (
          <div className="rounded-[12px] border border-[var(--border-faint)] bg-[var(--surface-panel)] p-3 space-y-2.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <Pill variant="meta">{`${lifecycle.total} total`}</Pill>
              <Pill variant="meta">{`${lifecycle.counts.draft} draft`}</Pill>
              <Pill variant="meta">{`${lifecycle.counts.pending_approval} pending`}</Pill>
              <Pill variant="meta">{`${lifecycle.counts.approved} approved`}</Pill>
              <Pill variant="meta">{`${lifecycle.counts.rejected} rejected`}</Pill>
              <Pill variant="meta">{`${lifecycle.counts.superseded} superseded`}</Pill>
              <Pill level={lifecycle.attentionCount > 0 ? "degraded" : "healthy"}>
                {attentionLabel}
              </Pill>
            </div>
            <InlineAlert tone={attentionTone} testId="source-versions-attention">
              <div className="space-y-1">
                <p className="font-semibold text-[var(--foreground)]">
                  {launchRollup ? launchRollup.headline : lifecycle.nextAction}
                </p>
                <p className="text-[var(--foreground-muted)]">
                  {launchRollup ? launchRollup.detail : lifecycle.nextActionDetail}
                </p>
                {lifecycle.latestVersion ? (
                  <p className="text-[12px] text-[var(--foreground-subtle)]">
                    Latest version: {lifecycle.latestVersion.version_label} (
                    {describeSourceVersionStatus(lifecycle.latestVersion.status).label}) · updated{" "}
                    {formatSwissDateTime(lifecycle.latestVersion.updated_at)}
                  </p>
                ) : null}
              </div>
            </InlineAlert>
          </div>
        ) : null}

        {!versions.isPending && !versions.error && lifecycle.total === 0 ? (
          <div className="rounded-[12px] border border-[var(--border-faint)] bg-[var(--surface-panel)] p-4 space-y-2">
            <p className="text-[13px] font-semibold text-[var(--foreground)]">
              No source versions yet
            </p>
            <p className="text-[13px] text-[var(--foreground-subtle)]">
              Create the first draft version to establish the lifecycle for this source.
            </p>
            <Button variant="primary" onClick={openCreateDialog}>
              Create version
            </Button>
          </div>
        ) : null}

        {rows.length > 0 ? (
          <div className="overflow-x-auto rounded-[12px] border border-[var(--border)]">
            <table className="min-w-full border-collapse text-sm text-[var(--foreground)]">
              <thead>
                <tr className="bg-[var(--surface-input)] text-left">
                  {[
                    "Version",
                    "Status",
                    "Extractor profile",
                    "Acquisition config",
                    "Updated",
                    "Actions",
                  ].map((heading) => (
                    <th
                      key={heading}
                      className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-meta)]"
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((version, index) => {
                  // Edit / approve / reject are decided by version status alone,
                  // via `explainUnavailableVersionAction` inside
                  // `VersionActionButton` — one source of truth for both the
                  // `disabled` flag and the explanation the operator reads.
                  //
                  // The two *launch* actions need more than status (#667): a
                  // status-only rule cannot see an inert blueprint template, so
                  // launchability comes from the platform's own pre-flight.
                  // While the probe is in flight the buttons stay disabled and
                  // say "Checking…" — briefly refusing is honest; briefly
                  // promising is not.
                  const guards = guardsByVersion[version.source_version_id] ?? {
                    state: "checking" as const,
                    preview: { allowed: false, reason: "Checking run readiness…" },
                    production: { allowed: false, reason: "Checking run readiness…" },
                    summary: "Checking run readiness…",
                  };
                  const isActing = actionVersionId === version.source_version_id;
                  const statusMeta = describeSourceVersionStatus(version.status);
                  const previousVersion = index < rows.length - 1 ? rows[index + 1] : null;
                  const isDiffOpen = diffVersionId === version.source_version_id;

                  return (
                    <Fragment key={version.id}>
                      <tr className="border-t border-[var(--border-faint)] align-top">
                        <td className="px-4 py-3.5">
                          <div className="font-semibold text-[13px]">{version.version_label}</div>
                          <div className="font-mono text-[11px] text-[var(--foreground-subtle)]">
                            {version.source_version_id}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex flex-col items-start gap-1">
                            <Pill level={sourceVersionStatusToLevel(version.status)}>
                              {statusMeta.label}
                            </Pill>
                            {/*
                              `statusMeta.detail` for an approved version reads
                              "Ready for preview or production runs." — a claim
                              about launchability made from status alone. When
                              readiness disagrees, the readiness answer wins and
                              is shown in the row, not only in a tooltip that
                              keyboard and touch users never see (#667).
                            */}
                            {guards.summary ? (
                              <span
                                data-testid="version-launch-block"
                                className="text-[11px] font-medium text-[var(--status-degraded)]"
                              >
                                {guards.summary}
                              </span>
                            ) : (
                              <span className="text-[11px] text-[var(--foreground-subtle)]">
                                {statusMeta.detail}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3.5">{version.extractor_profile_id ?? "—"}</td>
                        <td className="px-4 py-3.5">
                          <pre className="m-0 max-w-[260px] overflow-hidden whitespace-pre-wrap rounded-md border border-[var(--border-faint)] bg-[var(--surface-input)] p-2 font-mono text-[11px] leading-[1.6] text-[var(--foreground-muted)]">
                            {summarizeAcquisitionSpec(version.acquisition_spec).join("\n")}
                          </pre>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap text-[12px] text-[var(--foreground-muted)]">
                          {formatSwissDateTime(version.updated_at)}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <VersionActionButton
                              action="edit"
                              status={version.status}
                              busy={isActing}
                              versionId={version.source_version_id}
                              onClick={() => openEditDialog(version)}
                            >
                              Edit
                            </VersionActionButton>
                            {previousVersion ? (
                              <Button
                                size="sm"
                                variant={isDiffOpen ? "primary" : "ghost"}
                                onClick={() =>
                                  setDiffVersionId(isDiffOpen ? null : version.source_version_id)
                                }
                              >
                                {isDiffOpen ? "Hide diff" : "Compare"}
                              </Button>
                            ) : null}
                            <VersionActionButton
                              action="preview"
                              status={version.status}
                              busy={isActing}
                              versionId={version.source_version_id}
                              variant="primary"
                              onClick={() => createRun("preview", version)}
                              guard={guards.preview}
                            >
                              {guards.state === "checking" ? "Checking…" : "Preview run"}
                            </VersionActionButton>
                            <span
                              aria-hidden
                              className="mx-0.5 hidden h-6 w-px self-center bg-[var(--border)] sm:inline-block"
                            />
                            <VersionActionButton
                              action="production"
                              status={version.status}
                              busy={isActing}
                              versionId={version.source_version_id}
                              onClick={() => setConfirm({ kind: "production", version })}
                              guard={guards.production}
                            >
                              {guards.state === "checking" ? "Checking…" : "Production run"}
                            </VersionActionButton>
                            <VersionActionButton
                              action="approve"
                              status={version.status}
                              busy={isActing}
                              versionId={version.source_version_id}
                              onClick={() => setConfirm({ kind: "approve", version })}
                            >
                              Approve
                            </VersionActionButton>
                            <VersionActionButton
                              action="reject"
                              status={version.status}
                              busy={isActing}
                              versionId={version.source_version_id}
                              className="border-[var(--status-critical)]/40 text-[var(--status-critical)] hover:border-[var(--status-critical)]"
                              onClick={() => setConfirm({ kind: "reject", version })}
                            >
                              Reject
                            </VersionActionButton>
                          </div>
                        </td>
                      </tr>
                      {isDiffOpen && previousVersion ? (
                        <tr className="border-t border-[var(--border-faint)] bg-[var(--surface-input)]">
                          <td colSpan={6} className="px-4 py-3">
                            <SourceVersionDiffPanel
                              previous={previousVersion}
                              current={version}
                              defaultOpen
                            />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      <Dialog
        open={dialogOpen}
        onClose={closeDialog}
        dismissable={!isSaving}
        title={editingVersion ? "Edit source version" : "Create source version"}
        footer={
          <>
            <Button variant="secondary" onClick={closeDialog} disabled={isSaving}>
              Cancel
            </Button>
            <Button variant="primary" onClick={submitDialog} disabled={isSaving}>
              {isSaving ? "Saving…" : "Save"}
            </Button>
          </>
        }
      >
        <SourceVersionForm formState={formState} onChange={setFormState} />
      </Dialog>

      <Dialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        size="sm"
        title={confirm ? CONFIRM_COPY[confirm.kind].title : ""}
        description={
          confirm ? CONFIRM_COPY[confirm.kind].describe(confirm.version.version_label) : undefined
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              className={confirm && CONFIRM_COPY[confirm.kind].danger ? DANGER_BUTTON : undefined}
              onClick={runConfirm}
            >
              {confirm ? CONFIRM_COPY[confirm.kind].confirmLabel : "Confirm"}
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-[var(--foreground-muted)]">
          This action updates the source-version lifecycle and may trigger downstream runs.
        </p>
      </Dialog>
    </Panel>
  );
}
