/**
 * `SourceShowV2` — v2 preview of the source detail page. Uses
 * `useShowController` + `useGetOne` for the source + reference lookups,
 * and `DetailGrid` / `FieldCell` from `src/ui/primitives/` for the M-9 /
 * M-15 / M-16 two-column field grid.
 *
 * Ported in #501 increment 2:
 *   - `SourceVersionsSectionV2` — the full source-version lifecycle surface
 *     (lifecycle rollup, version table, create/edit + confirm dialogs).
 *     Pure form/lifecycle logic is shared with the v1 MUI section via
 *     `./sourceVersionForm`; the diff view reuses `SourceVersionDiffPanel`.
 *
 * Ported in #501 increment 1:
 *   - `SourceHandoffPanel` — reads the legal-search handoff from the URL
 *     (`readLegalSearchHandoff`) and renders the gradient "why you are
 *     here / what to check next" card. The framework-agnostic guidance
 *     copy is shared with v1 via `./sourceHandoff`.
 */
"use client";

import { useGetOne, useShowController } from "ra-core";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import type {
  AuthorityRecord,
  JurisdictionRecord,
  SourceRecord,
} from "../../lib/admin/dataProvider";
import { type LegalSearchHandoff, readLegalSearchHandoff } from "../../lib/admin/navigationContext";
import { formatSwissDateTime } from "../../lib/format/date";
import { DetailGrid, FieldCell, Panel, Pill } from "../../ui/primitives";
import { sourceStatusToLevel } from "../shared/statusLevels";
import { SourceVersionsSectionV2 } from "./SourceVersionsSectionV2";
import { buildSourceHandoffGuidance } from "./sourceHandoff";

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

/**
 * Reads the legal-search handoff from the URL on mount (client-only, so it
 * stays behind a `useEffect`/`useState` guard to avoid an SSR/client
 * mismatch) and renders the gradient handoff card. Returns `null` when the
 * visit did not originate from legal search, so the card never appears on a
 * direct source-detail visit.
 */
function SourceHandoffPanel({ source }: { source: SourceRecord }) {
  const [handoff, setHandoff] = useState<LegalSearchHandoff | null>(null);

  useEffect(() => {
    setHandoff(readLegalSearchHandoff());
  }, []);

  if (!handoff) {
    return null;
  }

  const guidance = buildSourceHandoffGuidance(source, handoff);

  if (!guidance) {
    return null;
  }

  return (
    <Panel
      className="p-5 sm:p-6 space-y-3"
      style={{
        background: "linear-gradient(180deg, var(--brand-wash-4), var(--admin-panel-bg))",
      }}
    >
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Legal search handoff</h2>
        <p className="text-[13px] text-[var(--foreground-subtle)]">
          Why you are here and what to check next before changing this source.
        </p>
      </div>

      <p className="text-sm text-[var(--foreground-muted)]">{guidance.whyYouAreHere}</p>

      <div className="flex flex-wrap items-center gap-1.5">
        {handoff.query ? <Pill variant="meta">{handoff.query}</Pill> : null}
        {handoff.scopeLabel ? <Pill variant="meta">{handoff.scopeLabel}</Pill> : null}
        {handoff.selectedId ? (
          <Pill variant="meta">{`Selected item: ${handoff.selectedId}`}</Pill>
        ) : null}
      </div>

      <p className="text-sm text-[var(--foreground-muted)]">{guidance.whatToCheckNext}</p>
    </Panel>
  );
}

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
    return (
      <div className="px-4 py-10 text-center text-[var(--foreground-subtle)]">Loading source…</div>
    );
  }
  if (controller.error || !source) {
    return (
      <div className="px-4 py-10 text-center text-[var(--status-critical)]">
        Failed to load source.
      </div>
    );
  }

  const statusMeta = SOURCE_STATUS_META[source.status];

  return (
    <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-6">
      <SourceHandoffPanel source={source} />
      <header className="space-y-3">
        <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
          Source detail
        </p>
        <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
          {source.name}
        </h1>
        <div className="font-mono text-[12px] text-[var(--foreground-subtle)]">
          {source.source_id}
        </div>
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
      <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-5 sm:p-6 shadow-[var(--shadow-card)] backdrop-blur-[12px] space-y-1.5">
        <h2 className="text-[15px] font-semibold text-[var(--foreground)]">Source lifecycle</h2>
        <p className="text-[13px] text-[var(--foreground-subtle)]">
          Status, operating posture, and the main attention cue for this source.
        </p>
        <p className="text-sm text-[var(--foreground-muted)] pt-1">{statusMeta.detail}</p>
      </section>

      <DetailGrid>
        <FieldCell label="Source ID">
          <span className="font-mono text-[13px]">{source.source_id}</span>
        </FieldCell>
        <FieldCell label="Name">{source.name}</FieldCell>
        <FieldCell label="Description" span="full">
          {source.description ?? <span className="text-[var(--foreground-faint)]">—</span>}
        </FieldCell>
        <FieldCell label="Jurisdiction">
          {jurisdiction ? (
            <>
              {jurisdiction.name}{" "}
              <span className="text-[var(--foreground-subtle)]">({jurisdiction.slug})</span>
            </>
          ) : (
            <span className="text-[var(--foreground-faint)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Authority">
          {authority ? (
            <>
              {authority.name}{" "}
              <span className="text-[var(--foreground-subtle)]">({authority.slug})</span>
            </>
          ) : (
            <span className="text-[var(--foreground-faint)]">—</span>
          )}
        </FieldCell>
        <FieldCell label="Document family">
          {source.document_family ?? <span className="text-[var(--foreground-faint)]">—</span>}
        </FieldCell>
        <FieldCell label="Source type">{source.source_type}</FieldCell>
        <FieldCell label="Created">{formatSwissDateTime(source.created_at)}</FieldCell>
        <FieldCell label="Updated">{formatSwissDateTime(source.updated_at)}</FieldCell>
      </DetailGrid>

      <SourceVersionsSectionV2 source={source} />
    </div>
  );
}
