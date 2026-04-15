"use client";

import { Chip, Stack, Typography } from "@mui/material";
import { Datagrid, DateField, FunctionField, List, ReferenceField, TextField } from "react-admin";
import type {
  AuthorityRecord,
  JurisdictionRecord,
  SourceRecord,
} from "../../lib/admin/dataProvider";
import { formatReferenceLabel } from "../shared/referenceUtils";
import { StatusBadge, sourceStatusToLevel } from "../shared/StatusBadge";

const SOURCE_STATUS_META = {
  active: {
    label: "Active",
    color: "success" as const,
    detail: "Eligible for new versions and runs.",
  },
  inactive: {
    label: "Inactive",
    color: "warning" as const,
    detail: "Paused until an operator reactivates it.",
  },
  archived: {
    label: "Archived",
    color: "default" as const,
    detail: "Read-only history.",
  },
} as const;

export function SourceList() {
  return (
    <List
      resource="sources"
      title="Sources"
      perPage={50}
      sort={{ field: "updated_at", order: "DESC" }}
    >
      <Datagrid rowClick="show" bulkActionButtons={false}>
        <FunctionField<SourceRecord>
          label="Source"
          render={(record) => (
            <Stack spacing={0.35}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {record?.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {record?.source_id}
              </Typography>
            </Stack>
          )}
        />
        <FunctionField<SourceRecord>
          label="Lifecycle"
          render={(record) => {
            if (!record) {
              return null;
            }
            const statusMeta = SOURCE_STATUS_META[record.status];
            return (
              <Stack spacing={0.5}>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                  <StatusBadge
                    level={sourceStatusToLevel(record.status)}
                    label={statusMeta.label}
                  />
                  <Chip size="small" variant="outlined" label={record.source_type} />
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  {statusMeta.detail}
                </Typography>
              </Stack>
            );
          }}
        />
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
        <TextField source="document_family" label="Family" emptyText="-" />
        <DateField source="updated_at" label="Updated" showTime />
      </Datagrid>
    </List>
  );
}
