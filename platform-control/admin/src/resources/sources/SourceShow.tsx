"use client";

import { Box, Chip, Paper, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import {
  DateField,
  FunctionField,
  ReferenceField,
  Show,
  SimpleShowLayout,
  TextField,
  useRecordContext,
} from "react-admin";
import type {
  AuthorityRecord,
  JurisdictionRecord,
  SourceRecord,
} from "../../lib/admin/dataProvider";
import {
  describeLegalSearchHandoff,
  type LegalSearchHandoff,
  readLegalSearchHandoff,
} from "../../lib/admin/navigationContext";
import { PageContextBar } from "../shared/PageContextBar";
import { formatReferenceLabel } from "../shared/referenceUtils";
import { StatusBadge, sourceStatusToLevel } from "../shared/StatusBadge";
import { SourceVersionsSection } from "./SourceVersionsSection";

const SOURCE_STATUS_META = {
  active: {
    label: "Active",
    detail: "This source can receive new versions and launch new runs.",
  },
  inactive: {
    label: "Inactive",
    detail: "This source is paused. Reactivate it before launching new work.",
  },
  archived: {
    label: "Archived",
    detail: "This source is retained for history and should be treated as read-only.",
  },
} as const;

export type SourceHandoffGuidance = {
  whyYouAreHere: string;
  whatToCheckNext: string;
};

export function buildSourceHandoffGuidance(
  source: SourceRecord,
  handoff: LegalSearchHandoff,
): SourceHandoffGuidance | null {
  if (!handoff.hasOrigin) {
    return null;
  }

  const contextSummary = describeLegalSearchHandoff(handoff);
  const whyYouAreHere = `You came from legal search. ${contextSummary}.`;
  const whatToCheckNext =
    source.status === "active"
      ? `${source.name} is active, so confirm the jurisdiction, authority, and version history below before you treat it as the source behind the selected search item.`
      : source.status === "inactive"
        ? `${source.name} is inactive, so check whether it should be reactivated before any work continues on the selected search item.`
        : `${source.name} is archived, so treat the record as read-only and confirm whether the selected search item should point to a different source.`;

  return {
    whyYouAreHere,
    whatToCheckNext,
  };
}

function SourceLifecyclePanel() {
  const source = useRecordContext<SourceRecord>();

  if (!source) {
    return null;
  }

  const statusMeta = SOURCE_STATUS_META[source.status];

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="subtitle2">Source lifecycle</Typography>
          <Typography variant="body2" color="text.secondary">
            Status, operating posture, and the main attention cue for this source.
          </Typography>
        </Box>

        <Stack direction="row" spacing={1.5} alignItems="center">
          <StatusBadge level={sourceStatusToLevel(source.status)} label={statusMeta.label} />
          <Typography variant="body2" color="text.secondary">
            {statusMeta.detail}
          </Typography>
        </Stack>
      </Stack>
    </Paper>
  );
}

function SourcePageContextBar() {
  const source = useRecordContext<SourceRecord>();

  if (!source) {
    return null;
  }

  return (
    <PageContextBar>
      <Stack spacing={1.25}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          {source.name}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ fontFamily: "monospace" }}>
          {source.source_id}
        </Typography>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          <StatusBadge level={sourceStatusToLevel(source.status)} label={SOURCE_STATUS_META[source.status].label} />
          <Chip size="small" variant="outlined" label={`Type: ${source.source_type}`} />
          <Chip
            size="small"
            variant="outlined"
            label={`Family: ${source.document_family ?? "none"}`}
          />
        </Stack>
      </Stack>
    </PageContextBar>
  );
}

function SourceHandoffPanel() {
  const source = useRecordContext<SourceRecord>();
  const [handoff, setHandoff] = useState<LegalSearchHandoff | null>(null);

  useEffect(() => {
    setHandoff(readLegalSearchHandoff());
  }, []);

  if (!source || !handoff) {
    return null;
  }

  const guidance = buildSourceHandoffGuidance(source, handoff);

  if (!guidance) {
    return null;
  }

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        mb: 2,
        background: "linear-gradient(180deg, rgba(15, 76, 129, 0.035), rgba(255, 255, 255, 0.97))",
      }}
    >
      <Stack spacing={1.5}>
        <Box>
          <Typography variant="subtitle2">Legal search handoff</Typography>
          <Typography variant="body2" color="text.secondary">
            Why you are here and what to check next before changing this source.
          </Typography>
        </Box>

        <Typography variant="body2" color="text.secondary">
          {guidance.whyYouAreHere}
        </Typography>

        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          {handoff.query ? <Chip size="small" variant="outlined" label={handoff.query} /> : null}
          {handoff.scopeLabel ? (
            <Chip size="small" variant="outlined" label={handoff.scopeLabel} />
          ) : null}
          {handoff.selectedId ? (
            <Chip size="small" variant="outlined" label={`Selected item: ${handoff.selectedId}`} />
          ) : null}
        </Stack>

        <Typography variant="body2" color="text.secondary">
          {guidance.whatToCheckNext}
        </Typography>
      </Stack>
    </Paper>
  );
}

export function SourceShow() {
  return (
    <Show resource="sources" title="Source">
      <SimpleShowLayout>
        <SourceHandoffPanel />
        <SourcePageContextBar />
        <SourceLifecyclePanel />
        <TextField source="source_id" label="Source ID" />
        <TextField source="name" label="Name" />
        <TextField source="description" label="Description" emptyText="-" />
        <ReferenceField
          source="jurisdiction_id"
          reference="jurisdictions"
          label="Jurisdiction"
          link={false}
        >
          <FunctionField<JurisdictionRecord> render={(record) => formatReferenceLabel(record)} />
        </ReferenceField>
        <ReferenceField
          source="authority_id"
          reference="authorities"
          label="Authority"
          link={false}
        >
          <FunctionField<AuthorityRecord> render={(record) => formatReferenceLabel(record)} />
        </ReferenceField>
        <TextField source="document_family" label="Document family" emptyText="-" />
        <TextField source="source_type" label="Source type" />
        <DateField source="created_at" label="Created" showTime />
        <DateField source="updated_at" label="Updated" showTime />
        <SourceVersionsSection />
      </SimpleShowLayout>
    </Show>
  );
}
