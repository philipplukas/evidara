/**
 * `SourceCreate` — the source-create wizard. Uses `ra-core`'s `<Form>` +
 * `useDataProvider`; every input is a Tailwind + radix primitive
 * (`TextInput` / `Select`), so the page has zero MUI imports. Wired via
 * `<Resource create>` at `/sources/create` (ADR-0026: this Tailwind wizard
 * replaced the retired MUI wizard once it reached parity — see #501).
 *
 * Creates the source and its initial source version in one submit via the
 * `source-create-wizard` data-provider resource (`POST
 * /v1/sources/with-version`). The operator picks a country overlay + provider
 * template; the expanded, server-side `acquisition_spec` is previewed live via
 * `controlPlaneActions.previewSourceBlueprint` in `SourceBlueprintPreviewPanel`.
 *
 * Authority choices are filtered live from the watched `jurisdiction_id` via
 * `filterAuthoritiesByJurisdiction` and validated with
 * `isAuthorityValidForJurisdiction`, so picking a mismatched authority fails at
 * submit. The pure preview/overlay/template helpers live in `./sourceBlueprint`.
 */
"use client";

import { Form, required, useDataProvider, useGetList, useNotify } from "ra-core";
import { useEffect, useRef, useState } from "react";
import { useWatch } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import type {
  AuthorityRecord,
  JurisdictionRecord,
  SourceBlueprintPreview,
  SourceBlueprintTemplate,
} from "../../lib/admin/dataProvider";
import { controlPlaneActions } from "../../lib/admin/dataProvider";
import { Button, InlineAlert, Select, type SelectChoice, TextInput } from "../../ui/primitives";
import {
  filterAuthoritiesByJurisdiction,
  formatReferenceLabel,
  isAuthorityValidForJurisdiction,
} from "../shared/referenceUtils";
import {
  buildOverlayChoices,
  buildTemplateChoicesByOverlay,
  summarizePreview,
} from "./sourceBlueprint";

const REFERENCE_LIST_PARAMS = {
  pagination: { page: 1, perPage: 250 },
  sort: { field: "name", order: "ASC" as const },
};

const SOURCE_TYPE_CHOICES: SelectChoice[] = [
  { id: "website", name: "Website (crawl)" },
  { id: "api", name: "API (structured)" },
];

const CREATE_DEFAULTS = {
  source_type: "website",
  version_label: "v1",
  description: null as string | null,
  document_family: null as string | null,
  jurisdiction_id: null as string | null,
  authority_id: null as string | null,
  extractor_profile_id: null as string | null,
  overlay_id: null as string | null,
  provider_template_id: null as string | null,
};

type SourceWizardFormData = {
  name: string;
  description?: string | null;
  jurisdiction_id: string;
  authority_id: string;
  source_type: "website" | "api";
  document_family?: string | null;
  version_label: string;
  extractor_profile_id?: string | null;
  overlay_id: string;
  provider_template_id: string;
};

// Inner component: reads `jurisdiction_id` with `useWatch` so the authority
// `<Select>` re-renders with a filtered choice list whenever the operator
// changes jurisdiction. Splitting it out keeps the `useWatch` call inside the
// `<Form>`-provided react-hook-form context.
function AuthoritySelectField({ authorities }: { authorities: AuthorityRecord[] }) {
  const currentJurisdictionId = useWatch({ name: "jurisdiction_id" }) as string | null | undefined;

  const choices: SelectChoice[] = filterAuthoritiesByJurisdiction(
    authorities,
    currentJurisdictionId,
  ).map((authority) => ({
    id: authority.authority_id,
    name: formatReferenceLabel(authority),
  }));

  const validateAuthority = (value: unknown) => {
    if (value === null || value === undefined || value === "") {
      return undefined;
    }
    if (typeof value !== "string") {
      return "Select a valid authority.";
    }
    if (!isAuthorityValidForJurisdiction(authorities, value, currentJurisdictionId)) {
      return currentJurisdictionId
        ? "Select an authority within the chosen jurisdiction or a global authority."
        : "Select a global authority or choose a jurisdiction first.";
    }
    return undefined;
  };

  return (
    <Select
      // Force remount on jurisdiction change so the trigger re-reads its
      // value against the new choice set — same trick the v1 page uses with
      // `key={formData.jurisdiction_id}` on `AuthoritySelectInput`.
      key={currentJurisdictionId ?? "no-jurisdiction"}
      source="authority_id"
      label="Authority"
      choices={choices}
      required
      validate={[required(), validateAuthority]}
      helperText={
        currentJurisdictionId
          ? "Only authorities in the selected jurisdiction are shown."
          : "Select a jurisdiction first to load the matching authorities."
      }
      placeholder={currentJurisdictionId ? "Select an authority…" : "Select a jurisdiction first"}
    />
  );
}

// Inner component: reads `overlay_id` with `useWatch` so the provider-template
// `<Select>` re-renders with the choices for the picked overlay. Mirrors the
// v1 `FormDataConsumer` that keys the template select off `formData.overlay_id`.
function ProviderTemplateSelectField({
  templateChoicesByOverlay,
}: {
  templateChoicesByOverlay: Record<string, SelectChoice[]>;
}) {
  const overlayId = useWatch({ name: "overlay_id" }) as string | null | undefined;
  const choices = templateChoicesByOverlay[overlayId ?? ""] ?? [];

  return (
    <Select
      key={overlayId ?? "no-overlay"}
      source="provider_template_id"
      label="Provider template"
      choices={choices}
      required
      validate={required()}
      helperText={
        choices.length > 0
          ? "Template is expanded server-side into validated acquisition_spec."
          : "No template configured for this overlay yet."
      }
      placeholder={overlayId ? "Select a provider template…" : "Select an overlay first"}
    />
  );
}

// Inner component: watches overlay + provider template, debounces a
// server-side blueprint preview, and renders the expanded acquisition-spec
// summary (with an optional raw-JSON view). Tailwind port of the v1
// `SourceBlueprintPreviewPanel`.
function SourceBlueprintPreviewPanel() {
  const overlayId = useWatch({ name: "overlay_id" }) as string | null | undefined;
  const providerTemplateId = useWatch({ name: "provider_template_id" }) as
    | string
    | null
    | undefined;
  const [preview, setPreview] = useState<SourceBlueprintPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showRawJson, setShowRawJson] = useState(false);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    if (!overlayId || !providerTemplateId) {
      setPreview(null);
      setError(null);
      return;
    }

    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    setError(null);
    setIsLoading(true);
    const timeoutId = window.setTimeout(() => {
      void controlPlaneActions
        .previewSourceBlueprint({
          overlay_id: overlayId,
          provider_template_id: providerTemplateId,
        })
        .then((next) => {
          if (requestSeqRef.current !== requestSeq) return;
          setPreview(next);
        })
        .catch((err: unknown) => {
          if (requestSeqRef.current !== requestSeq) return;
          setPreview(null);
          setError(err instanceof Error ? err.message : "Unable to preview blueprint.");
        })
        .finally(() => {
          if (requestSeqRef.current !== requestSeq) return;
          setIsLoading(false);
        });
    }, 250);

    return () => window.clearTimeout(timeoutId);
  }, [overlayId, providerTemplateId]);

  if (!overlayId || !providerTemplateId) {
    return (
      <InlineAlert tone="info">
        Select overlay and provider template to preview expanded acquisition config.
      </InlineAlert>
    );
  }

  if (isLoading) {
    return <InlineAlert tone="info">Loading expanded acquisition config…</InlineAlert>;
  }

  if (error) {
    return (
      <InlineAlert tone="error" testId="blueprint-preview-error">
        {error}
      </InlineAlert>
    );
  }

  if (!preview) {
    return null;
  }

  return (
    <InlineAlert tone="info" testId="blueprint-preview">
      <div className="space-y-2">
        <p className="font-semibold text-[var(--foreground)]">Expanded acquisition spec preview</p>
        <div className="space-y-0.5 text-[13px] text-[var(--foreground)]">
          {summarizePreview(preview).map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
        <Button variant="secondary" size="sm" onClick={() => setShowRawJson((current) => !current)}>
          {showRawJson ? "Hide raw JSON" : "Show raw JSON"}
        </Button>
        {showRawJson ? (
          <pre className="m-0 mt-1 whitespace-pre-wrap text-[12px] text-[var(--foreground)]">
            {JSON.stringify(preview.acquisition_spec, null, 2)}
          </pre>
        ) : null}
      </div>
    </InlineAlert>
  );
}

// Inner component: watches overlay/template/version so the "review generated
// config" summary reflects the current picks. Mirrors the v1 review alert.
function ReviewSummary() {
  const overlayId = useWatch({ name: "overlay_id" }) as string | null | undefined;
  const providerTemplateId = useWatch({ name: "provider_template_id" }) as
    | string
    | null
    | undefined;
  const versionLabel = useWatch({ name: "version_label" }) as string | null | undefined;

  return (
    <InlineAlert tone="info">
      Review generated config: overlay <strong>{overlayId ?? "n/a"}</strong>, template{" "}
      <strong>{providerTemplateId ?? "n/a"}</strong>, version label{" "}
      <strong>{versionLabel ?? "n/a"}</strong>.
    </InlineAlert>
  );
}

export default function SourceCreate() {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [templates, setTemplates] = useState<SourceBlueprintTemplate[]>([]);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  const jurisdictions = useGetList<JurisdictionRecord>("jurisdictions", REFERENCE_LIST_PARAMS);
  const authorities = useGetList<AuthorityRecord>("authorities", REFERENCE_LIST_PARAMS);

  useEffect(() => {
    let active = true;
    void controlPlaneActions
      .listSourceBlueprintTemplates()
      .then((data) => {
        if (!active) return;
        setTemplates(data);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setTemplatesError(
          err instanceof Error ? err.message : "Unable to load source blueprint templates.",
        );
      });
    return () => {
      active = false;
    };
  }, []);

  const jurisdictionChoices: SelectChoice[] = (jurisdictions.data ?? []).map((jurisdiction) => ({
    id: jurisdiction.jurisdiction_id,
    name: formatReferenceLabel(jurisdiction),
  }));

  const overlayChoices = buildOverlayChoices(templates);
  const templateChoicesByOverlay = buildTemplateChoicesByOverlay(templates);

  const handleSubmit = async (values: Record<string, unknown>) => {
    const form = values as SourceWizardFormData;
    setSaving(true);
    try {
      const result = await dataProvider.create("source-create-wizard", {
        data: {
          source: {
            name: form.name,
            description: form.description,
            jurisdiction_id: form.jurisdiction_id,
            authority_id: form.authority_id,
            source_type: form.source_type,
            document_family: form.document_family,
          },
          source_version: {
            version_label: form.version_label,
            extractor_profile_id: form.extractor_profile_id,
            overlay_id: form.overlay_id,
            provider_template_id: form.provider_template_id,
          },
        },
      });
      notify("Source and initial version created from overlay template.", { type: "success" });
      navigate(`/sources/${result.data.id}/show`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      notify(`Could not create source: ${message}`, { type: "error" });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-3xl mx-auto space-y-6">
      <header className="space-y-2">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--text-meta)]">
          Source setup
        </p>
        <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          Create source
        </h1>
        <p className="text-[14px] text-[var(--text-meta)] max-w-[72ch]">
          Create the source and its initial source version in one wizard flow. Choose a country
          overlay and provider template, review the expanded config, then save.
        </p>
      </header>

      {templatesError ? <InlineAlert tone="error">{templatesError}</InlineAlert> : null}

      <Form onSubmit={handleSubmit} defaultValues={CREATE_DEFAULTS} sanitizeEmptyValues>
        <div className="rounded-[18px] border border-[var(--border)] bg-[var(--surface-panel)] p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-5">
          <TextInput
            source="name"
            label="Name"
            required
            validate={required()}
            helperText="Operator-facing display name."
            placeholder="e.g. Swiss Federal Court"
          />
          <TextInput
            source="description"
            label="Description"
            multiline
            helperText="Optional internal notes for operators reviewing this source."
          />
          <Select
            source="jurisdiction_id"
            label="Jurisdiction"
            choices={jurisdictionChoices}
            required
            validate={required()}
            helperText="Choose the legal boundary this source belongs to."
            placeholder="Select a jurisdiction…"
          />
          <AuthoritySelectField authorities={authorities.data ?? []} />
          <TextInput
            source="document_family"
            label="Document family"
            helperText="Optional grouping label surfaced during operator review."
          />
          <Select
            source="source_type"
            label="Source type"
            choices={SOURCE_TYPE_CHOICES}
            required
            validate={required()}
            helperText="Website for Firecrawl crawls, API for structured endpoints like RIS OGD."
            placeholder="Select a source type…"
          />
          <TextInput
            source="version_label"
            label="Initial version label"
            required
            validate={required()}
            helperText="Creates the first source version together with the source."
            placeholder="v1"
          />
          <TextInput
            source="extractor_profile_id"
            label="Extractor profile ID"
            helperText="Optional. Leave empty to use provider/default extraction path."
          />
          <Select
            source="overlay_id"
            label="Country overlay"
            choices={overlayChoices}
            required
            validate={required()}
            helperText="Overlay package driving provider template defaults."
            placeholder="Select a country overlay…"
          />
          <ProviderTemplateSelectField templateChoicesByOverlay={templateChoicesByOverlay} />

          <ReviewSummary />
          <SourceBlueprintPreviewPanel />

          <footer className="flex items-center justify-end gap-2 pt-2 border-t border-[var(--border)]">
            <Button variant="ghost" onClick={() => navigate("/sources")} type="button">
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={saving}>
              {saving ? "Creating…" : "Create source"}
            </Button>
          </footer>
        </div>
      </Form>
    </div>
  );
}
