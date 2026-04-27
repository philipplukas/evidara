/**
 * `SourceShowV2` — v2 preview of the source detail page. Uses
 * `useShowController` + `useGetOne` for the source + reference lookups,
 * and `DetailGrid` / `FieldCell` from `src/ui/primitives/` for the M-9 /
 * M-15 / M-16 two-column field grid.
 *
 * Deferred until follow-up increments (documented inline in the deferred-
 * panel footnote at the bottom of the page):
 *   - `SourceHandoffPanel` — stateful URL-param read; ports with the
 *     shell migration.
 *   - `SourceVersionsSection` — mutations, dialogs, tables; ports with
 *     the Select primitive in the SourceCreate increment.
 */
"use client";

import { useGetOne, useShowController } from "ra-core";
import { useParams } from "react-router-dom";
import type {
  AuthorityRecord,
  JurisdictionRecord,
  SourceRecord,
} from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { DetailGrid, FieldCell, Pill } from "../../ui/primitives";
import { sourceStatusToLevel } from "../shared/StatusBadge";

const SOURCE_STATUS_META: Record<SourceRecord["status"], { label: string; detail: string }> = {
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
};

export default function SourceShowV2() {
  const { id } = useParams();
  const controller = useShowController<SourceRecord>({
    resource: "sources",
    id,
  });
  const source = controller.record;

  const { data: jurisdiction } = useGetOne<JurisdictionRecord>(
    "jurisdictions",
    { id: source?.jurisdiction_id ?? "" },
    { enabled: !!source?.jurisdiction_id },
  );
  const { data: authority } = useGetOne<AuthorityRecord>(
    "authorities",
    { id: source?.authority_id ?? "" },
    { enabled: !!source?.authority_id },
  );

  if (controller.isPending) {
    return <div className="px-4 py-10 text-center text-[rgba(29,41,61,0.6)]">Loading source…</div>;
  }
  if (controller.error || !source) {
    return <div className="px-4 py-10 text-center text-[#b71c1c]">Failed to load source.</div>;
  }

  const statusMeta = SOURCE_STATUS_META[source.status];

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[1600px] mx-auto space-y-6">
      <header className="space-y-3">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[rgba(29,41,61,0.6)]">
          Source detail
        </p>
        <h1 className="font-sans text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          {source.name}
        </h1>
        <div className="font-mono text-[12px] text-[rgba(29,41,61,0.6)]">{source.source_id}</div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill level={sourceStatusToLevel(source.status)}>{statusMeta.label}</Pill>
          <Pill variant="meta">{`Type: ${source.source_type}`}</Pill>
          <Pill variant="meta">{`Family: ${source.document_family ?? "none"}`}</Pill>
        </div>
      </header>

      {/*
       * UX-12.4: the Active status pill is already present in the header
       * above, so the lifecycle card no longer renders a second copy on
       * the right. The card keeps its heading + description copy which
       * give context the header pills alone can't.
       */}
      <section className="rounded-[18px] border border-[rgba(29,41,61,0.08)] bg-[var(--admin-panel-bg)] p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-1.5">
        <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Source lifecycle</h2>
        <p className="text-[13px] text-[rgba(29,41,61,0.65)]">
          Status, operating posture, and the main attention cue for this source.
        </p>
        <p className="text-sm text-[rgba(29,41,61,0.75)] pt-1">{statusMeta.detail}</p>
      </section>

      <DetailGrid>
        <FieldCell label="Source ID">
          <span className="font-mono text-[13px]">{source.source_id}</span>
        </FieldCell>
        <FieldCell label="Name">{source.name}</FieldCell>
        <FieldCell label="Description" span="full">
          {source.description ?? <span className="text-[rgba(29,41,61,0.4)]">—</span>}
        </FieldCell>
        <FieldCell label="Jurisdiction">
          {jurisdiction ? (
            <>
              {jurisdiction.name}{" "}
              <span className="text-[rgba(29,41,61,0.55)]">({jurisdiction.slug})</span>
            </>
          ) : (
            <span className="text-[rgba(29,41,61,0.4)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Authority">
          {authority ? (
            <>
              {authority.name}{" "}
              <span className="text-[rgba(29,41,61,0.55)]">({authority.slug})</span>
            </>
          ) : (
            <span className="text-[rgba(29,41,61,0.4)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Document family">
          {source.document_family ?? <span className="text-[rgba(29,41,61,0.4)]">—</span>}
        </FieldCell>
        <FieldCell label="Source type">{source.source_type}</FieldCell>
        <FieldCell label="Created">{formatSwissDateTime(source.created_at)}</FieldCell>
        <FieldCell label="Updated">{formatSwissDateTime(source.updated_at)}</FieldCell>
      </DetailGrid>
    </div>
  );
}
