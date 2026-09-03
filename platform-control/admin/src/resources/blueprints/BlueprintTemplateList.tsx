/**
 * `BlueprintTemplateList` — the operator's coverage inventory (#668).
 *
 * `GET /v1/sources/blueprint-templates` has always returned every template with
 * its ADR-0030 lock state, and nothing rendered it. The only way to discover
 * that a template was inert was to start a source-create wizard and select it,
 * one at a time — so the fact that a third of the catalogue is unlaunchable, and
 * that a chunk of *that* needs nothing but the key an operator already owns, was
 * invisible. This screen is that inventory, and it is the surface #628 means by
 * "evidence-gated coverage": see what is live, what is inert, and *which key is
 * shut*, before investing in a source.
 *
 * The design commitment is that the two keys must be legible and distinct.
 * `enabled` is config — an operator flips it here after capturing acceptance-run
 * evidence. `live_ready` is code — no operator action opens it. The "Awaiting
 * evidence" preset is therefore the most important control on the page: it is
 * the operator's own worklist, filtered down from the noise of templates that
 * are somebody else's problem.
 */
"use client";

import { ListContextProvider, useListController } from "ra-core";
import { useMemo, useState } from "react";
import {
  classifyTemplate,
  describeCodeKey,
  describeConfigKey,
  describeEnablementAction,
  describeProvenance,
  type KeyDescriptor,
  LOCK_CLASS_ORDER,
  summarizeInventory,
  type TemplateLockClass,
} from "../../domain/blueprintLock";
import { ResourceName } from "../../domain/resourceNames";
import type { SourceBlueprintTemplate } from "../../lib/admin/dataProvider";
import { formatSwissDateTime } from "../../lib/format/date";
import { Button, DataTable, type DataTableColumn, Pill } from "../../ui/primitives";
import { BlueprintEnablementDialog } from "./BlueprintEnablementDialog";

type TemplateRecord = SourceBlueprintTemplate & { id: string };

const CLASS_PRESET_LABEL: Record<TemplateLockClass, string> = {
  "operator-actionable": "Ready to enable — you can fix",
  "awaiting-acceptance": "Awaiting acceptance run — you can fix",
  "engineer-blocked": "Needs provider work",
  live: "Live",
};

function PresetButton({
  isActive,
  onClick,
  children,
}: {
  isActive: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      className={`inline-flex items-center rounded-full border px-3 h-8 text-[12px] font-semibold transition-colors ${
        isActive
          ? "bg-[var(--brand-wash-8)] border-[var(--brand)]/50 text-[var(--brand)]"
          : "bg-[var(--surface-panel)] border-[var(--border)] text-[var(--foreground-muted)] hover:border-[var(--border-strong)]"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * One key of the lock: the pill states *what* it is, the line under it states
 * *whose* it is. Stacked rather than side-by-side — at this column width a
 * horizontal pair wraps the pill label onto two lines and the hint drifts out
 * of alignment with the key it belongs to.
 */
function KeyRow({ descriptor }: { descriptor: KeyDescriptor }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div>
        <Pill level={descriptor.level} className="whitespace-nowrap">
          {descriptor.label}: {descriptor.state}
        </Pill>
      </div>
      <span className="text-[11px] text-[var(--foreground-subtle)] leading-snug">
        {descriptor.ownerHint}
      </span>
    </div>
  );
}

export default function BlueprintTemplateList() {
  const controller = useListController<TemplateRecord>({
    resource: ResourceName.BlueprintTemplates,
    perPage: 50,
    sort: { field: "overlay_id", order: "ASC" },
  });
  const [pendingFlip, setPendingFlip] = useState<SourceBlueprintTemplate | null>(null);

  const records = useMemo(() => controller.data ?? [], [controller.data]);
  const filterValues = controller.filterValues as { lock_class?: TemplateLockClass };
  const activeClass = filterValues.lock_class;

  // Counts describe the page in hand. The endpoint is unbounded and perPage is
  // 50 against ~31 templates, so in practice that is the whole catalogue — but
  // the copy says "in view" rather than asserting a total the page cannot see.
  const summary = useMemo(() => summarizeInventory(records), [records]);

  const setClass = (lockClass: TemplateLockClass | undefined) =>
    controller.setFilters({ ...filterValues, lock_class: lockClass }, undefined, false);

  const columns: DataTableColumn<TemplateRecord>[] = [
    {
      key: "template",
      header: "Template",
      sortField: "provider_template_id",
      render: (record) => (
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-[var(--foreground)]">
            {record.provider_template_id}
          </span>
          <span className="text-[12px] text-[var(--foreground-subtle)]">
            overlay {record.overlay_id} · provider {record.provider}
          </span>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (record) => {
        const lockClass = classifyTemplate(record);
        return (
          <div className="flex flex-col gap-1 max-w-[40ch]">
            <Pill level={lockClass.level}>{lockClass.label}</Pill>
            <span className="text-[12px] text-[var(--foreground-subtle)]">{lockClass.detail}</span>
          </div>
        );
      },
    },
    {
      key: "keys",
      header: "Two-key lock",
      className: "min-w-[19ch] align-top",
      render: (record) => (
        <div className="flex flex-col gap-2">
          <KeyRow descriptor={describeConfigKey(record)} />
          <KeyRow descriptor={describeCodeKey(record)} />
        </div>
      ),
    },
    {
      key: "provenance",
      header: "Config key provenance",
      sortField: "source",
      render: (record) => (
        <div className="flex flex-col gap-0.5 max-w-[36ch]">
          <span className="text-[12px] text-[var(--foreground-muted)]">
            {describeProvenance(record)}
          </span>
          {record.note ? (
            <span className="text-[12px] text-[var(--foreground-subtle)] italic">
              “{record.note}”
            </span>
          ) : null}
          {record.updated_at ? (
            <span className="text-[11px] text-[var(--foreground-subtle)]">
              {formatSwissDateTime(record.updated_at)}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      headerClassName: "sr-only",
      className: "text-right",
      render: (record) => {
        const action = describeEnablementAction(record);
        return (
          <div className="flex flex-col items-end gap-1">
            <Button size="sm" variant={action.variant} onClick={() => setPendingFlip(record)}>
              {action.label}
            </Button>
            {action.futility ? (
              <span
                data-testid="enablement-futility-note"
                className="max-w-[22ch] text-right text-[11px] leading-snug text-[var(--foreground-subtle)]"
              >
                {action.futility}
              </span>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <ListContextProvider value={controller}>
      <div className="px-4 py-6 sm:px-6 sm:py-8 max-w-[var(--container-max)] mx-auto space-y-4">
        <header className="space-y-2">
          <p className="text-[11px] uppercase tracking-[0.16em] font-semibold text-[var(--foreground-subtle)]">
            Coverage inventory
          </p>
          <h1 className="font-[family:var(--font-admin-serif)] text-[28px] font-semibold text-[var(--foreground)] leading-tight">
            Blueprints
          </h1>
          <p className="text-[14px] text-[var(--foreground-muted)] max-w-[78ch]">
            Every shipped blueprint template and the state of its ADR-0030 two-key lock. A live run
            fires only when both keys are turned. The <strong>config key</strong> is yours: capture
            acceptance-run evidence, then enable the template here — no repo edit, no deploy. The{" "}
            <strong>code key</strong> is the provider asserting it can physically acquire the
            format; only an engineer can open it.
          </p>
        </header>

        <section className="rounded-[18px] border border-[var(--border-faint)] bg-[var(--admin-panel-bg)] p-4 space-y-3 shadow-[var(--shadow-card)] backdrop-blur-[12px]">
          <div className="flex flex-wrap items-center gap-1.5">
            {/*
             * Counts are suppressed while a filter is active. `summary` is
             * derived from the rows in hand, and the dataProvider filters this
             * endpoint client-side — so under a filter every count collapses to
             * the filtered set and "All templates 4" would be a lie about the
             * catalogue. Better to show no number than a wrong one.
             */}
            <PresetButton isActive={!activeClass} onClick={() => setClass(undefined)}>
              All templates{activeClass ? "" : ` ${summary.total}`}
            </PresetButton>
            {LOCK_CLASS_ORDER.map((lockClass) => (
              <PresetButton
                key={lockClass}
                isActive={activeClass === lockClass}
                onClick={() => setClass(lockClass)}
              >
                {CLASS_PRESET_LABEL[lockClass]}
                {activeClass ? "" : ` ${summary[lockClass]}`}
              </PresetButton>
            ))}
          </div>
          <p
            className="text-[12px] text-[var(--foreground-subtle)]"
            data-testid="inventory-summary"
          >
            {activeClass
              ? `${records.length} template${records.length === 1 ? "" : "s"} in view · filtered to ${CLASS_PRESET_LABEL[activeClass]}`
              : `${summary["operator-actionable"]} of ${summary.total} templates in view need only the config key you own.`}
          </p>
        </section>

        <DataTable<TemplateRecord>
          records={controller.data}
          columns={columns}
          getRowId={(record) => record.id}
          isLoading={controller.isPending}
          error={controller.error}
          sort={controller.sort}
          onSort={(field, order) => controller.setSort({ field, order })}
          total={controller.total}
          page={controller.page}
          perPage={controller.perPage}
          onPageChange={controller.setPage}
          empty={
            activeClass
              ? "No templates in this state — try another preset."
              : "No blueprint templates are shipped."
          }
        />
      </div>

      <BlueprintEnablementDialog template={pendingFlip} onClose={() => setPendingFlip(null)} />
    </ListContextProvider>
  );
}
