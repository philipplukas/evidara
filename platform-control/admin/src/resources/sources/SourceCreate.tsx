"use client";

import { Alert, Box, Button, Typography } from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Create,
  FormDataConsumer,
  required,
  SelectInput,
  SimpleForm,
  TextInput,
  useDataProvider,
  useNotify,
  useRedirect,
} from "react-admin";
import { useWatch } from "react-hook-form";
import { ResourceName } from "../../domain/resourceNames";
import {
  controlPlaneActions,
  type FedlexSparqlAcquisitionSpec,
  type SourceBlueprintPreview,
  type SourceBlueprintTemplate,
} from "../../lib/admin/dataProvider";
import { AuthoritySelectInput, JurisdictionSelectInput } from "../shared/ReferenceInputs";

const SOURCE_TYPE_CHOICES = [
  { id: "website", name: "Website (crawl)" },
  { id: "api", name: "API (structured)" },
];

const OVERLAY_NAMES: Record<string, string> = {
  at: "Austria (AT)",
  de: "Germany (DE)",
  ch: "Switzerland (CH)",
  fr: "France (FR)",
  it: "Italy (IT)",
};

type SourceWizardFormData = {
  name: string;
  description?: string;
  jurisdiction_id: string;
  authority_id: string;
  source_type: "website" | "api";
  document_family?: string;
  version_label: string;
  extractor_profile_id?: string;
  overlay_id: string;
  provider_template_id: string;
};

const summarizePreview = (preview: SourceBlueprintPreview): string[] => {
  const spec = preview.acquisition_spec;
  if (spec.provider === "ris_ogd") {
    return [
      `Provider: ${spec.provider}`,
      `Base URL: ${spec.base_url}`,
      `Applikation: ${spec.applikation ?? "all"}`,
      `Preferred formats: ${(spec.preferred_formats ?? []).join(", ") || "n/a"}`,
      `Page size/max pages: ${spec.page_size ?? "n/a"} / ${spec.max_pages ?? "n/a"}`,
    ];
  }
  if (spec.provider === "fedlex_sparql") {
    const fedlex = spec as FedlexSparqlAcquisitionSpec;
    const seeds = fedlex.seed_url
      ? [fedlex.seed_url, ...(fedlex.seed_urls ?? [])]
      : (fedlex.seed_urls ?? []);
    return [
      `Provider: ${fedlex.provider}`,
      `Seed work URIs: ${seeds.join(", ") || "n/a"}`,
      `SPARQL endpoint: ${fedlex.sparql_endpoint ?? "n/a"}`,
      `Preferred languages: ${(fedlex.preferred_languages ?? []).join(", ") || "n/a"}`,
      `Query mode/max expressions: ${fedlex.query_mode ?? "n/a"} / ${fedlex.max_expressions ?? "n/a"}`,
    ];
  }
  if (spec.provider === "deterministic_http") {
    const seeds = spec.seed_url
      ? [spec.seed_url, ...(spec.seed_urls ?? [])]
      : (spec.seed_urls ?? []);
    return [
      `Provider: ${spec.provider}`,
      `Seeds: ${seeds.join(", ") || "n/a"}`,
      `Tenant/corpus: ${spec.tenant_id ?? "n/a"} / ${spec.corpus_id ?? "n/a"}`,
    ];
  }
  const seeds = spec.seed_url ? [spec.seed_url, ...(spec.seed_urls ?? [])] : (spec.seed_urls ?? []);
  return [
    `Provider: ${spec.provider}`,
    `Mode: ${spec.mode}`,
    `Seeds: ${seeds.join(", ") || "n/a"}`,
    `Limit/depth: ${spec.limit ?? "n/a"} / ${spec.max_discovery_depth ?? "n/a"}`,
    `Formats: ${(spec.scrape_formats ?? []).join(", ") || "n/a"}`,
  ];
};

function SourceBlueprintPreviewPanel() {
  const overlayId = useWatch({ name: "overlay_id" }) as string | undefined;
  const providerTemplateId = useWatch({ name: "provider_template_id" }) as string | undefined;
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
      <Alert severity="info">
        Select overlay and provider template to preview expanded acquisition config.
      </Alert>
    );
  }

  if (isLoading) {
    return <Alert severity="info">Loading expanded acquisition config...</Alert>;
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!preview) {
    return null;
  }

  return (
    <Alert severity="info">
      <Typography variant="body2" sx={{ mb: 1 }}>
        Expanded acquisition spec preview
      </Typography>
      {summarizePreview(preview).map((line) => (
        <Typography key={line} variant="body2" sx={{ fontSize: 13 }}>
          {line}
        </Typography>
      ))}
      <Button
        size="small"
        sx={{ mt: 1 }}
        onClick={() => setShowRawJson((current) => !current)}
        variant="outlined"
      >
        {showRawJson ? "Hide raw JSON" : "Show raw JSON"}
      </Button>
      {showRawJson ? (
        <Box component="pre" sx={{ m: 0, mt: 1, whiteSpace: "pre-wrap", fontSize: 12 }}>
          {JSON.stringify(preview.acquisition_spec, null, 2)}
        </Box>
      ) : null}
    </Alert>
  );
}

export function SourceCreate() {
  const dataProvider = useDataProvider();
  const notify = useNotify();
  const redirect = useRedirect();
  const [templates, setTemplates] = useState<SourceBlueprintTemplate[]>([]);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

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

  const overlayChoices = useMemo(
    () =>
      Array.from(new Set(templates.map((template) => template.overlay_id))).map((overlayId) => ({
        id: overlayId,
        name: OVERLAY_NAMES[overlayId] ?? overlayId.toUpperCase(),
      })),
    [templates],
  );

  const templateChoicesByOverlay = useMemo(() => {
    const grouped: Record<string, Array<{ id: string; name: string }>> = {};
    for (const template of templates) {
      const list = grouped[template.overlay_id] ?? [];
      list.push({
        id: template.provider_template_id,
        name: `${template.provider_template_id} (${template.provider})`,
      });
      grouped[template.overlay_id] = list;
    }
    return grouped;
  }, [templates]);

  const handleSubmit = async (values: SourceWizardFormData) => {
    const result = await dataProvider.create("source-create-wizard", {
      data: {
        source: {
          name: values.name,
          description: values.description,
          jurisdiction_id: values.jurisdiction_id,
          authority_id: values.authority_id,
          source_type: values.source_type,
          document_family: values.document_family,
        },
        source_version: {
          version_label: values.version_label,
          extractor_profile_id: values.extractor_profile_id,
          overlay_id: values.overlay_id,
          provider_template_id: values.provider_template_id,
        },
      },
    });
    notify("Source and initial version created from overlay template.", { type: "success" });
    redirect("show", ResourceName.Sources, result.data.id, result.data);
  };

  return (
    <Create resource={ResourceName.Sources} title="Create Source">
      <SimpleForm
        defaultValues={{
          source_type: "website",
          overlay_id: templates[0]?.overlay_id ?? "at",
          provider_template_id: templates[0]?.provider_template_id ?? "",
          version_label: "v1",
        }}
        onSubmit={(values: Record<string, unknown>) => handleSubmit(values as SourceWizardFormData)}
        sanitizeEmptyValues
      >
        <Alert severity="info">
          Create the source and its initial source version in one wizard flow. Choose country
          overlay + provider template, review config summary, then save.
        </Alert>
        {templatesError ? <Alert severity="error">{templatesError}</Alert> : null}
        <TextInput source="name" label="Name" validate={required()} />
        <TextInput
          source="description"
          label="Description"
          multiline
          helperText="Optional internal notes for operators reviewing this source."
        />
        <JurisdictionSelectInput
          source="jurisdiction_id"
          label="Jurisdiction"
          helperText="Choose the legal boundary this source belongs to."
          validate={required()}
        />
        <FormDataConsumer<{ jurisdiction_id?: string | null }>>
          {({ formData }) => (
            <AuthoritySelectInput
              key={formData.jurisdiction_id ?? "no-jurisdiction"}
              source="authority_id"
              label="Authority"
              jurisdictionId={formData.jurisdiction_id ?? null}
              helperText={
                formData.jurisdiction_id
                  ? "Only authorities in the selected jurisdiction are shown."
                  : "Select a jurisdiction first to load the matching authorities."
              }
              validate={required()}
            />
          )}
        </FormDataConsumer>
        <TextInput
          source="document_family"
          label="Document family"
          helperText="Optional grouping label surfaced during operator review."
        />
        <SelectInput
          source="source_type"
          label="Source type"
          choices={SOURCE_TYPE_CHOICES}
          helperText="Website for Firecrawl crawls, API for structured endpoints like RIS OGD."
          validate={required()}
        />
        <TextInput
          source="version_label"
          label="Initial version label"
          helperText="Creates the first source version together with the source."
          validate={required()}
        />
        <TextInput
          source="extractor_profile_id"
          label="Extractor profile ID"
          helperText="Optional. Leave empty to use provider/default extraction path."
        />
        <SelectInput
          source="overlay_id"
          label="Country overlay"
          choices={overlayChoices}
          helperText="Overlay package driving provider template defaults."
          validate={required()}
        />
        <FormDataConsumer<{ overlay_id?: string | null }>>
          {({ formData }) => (
            <SelectInput
              source="provider_template_id"
              label="Provider template"
              choices={templateChoicesByOverlay[formData.overlay_id ?? ""] ?? []}
              helperText={
                (templateChoicesByOverlay[formData.overlay_id ?? ""] ?? []).length > 0
                  ? "Template is expanded server-side into validated acquisition_spec."
                  : "No template configured for this overlay yet."
              }
              validate={required()}
            />
          )}
        </FormDataConsumer>
        <FormDataConsumer<{
          overlay_id?: string;
          provider_template_id?: string;
          version_label?: string;
        }>>
          {({ formData }) => (
            <Alert severity="info">
              Review generated config: overlay <strong>{formData.overlay_id ?? "n/a"}</strong>,
              template <strong>{formData.provider_template_id ?? "n/a"}</strong>, version label{" "}
              <strong>{formData.version_label ?? "n/a"}</strong>.
            </Alert>
          )}
        </FormDataConsumer>
        <SourceBlueprintPreviewPanel />
      </SimpleForm>
    </Create>
  );
}
