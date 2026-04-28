/**
 * `SourceVersionDiffPanel` -- side-by-side diff of acquisition specs between
 * two source versions.
 *
 * Renders a key-by-key comparison of the JSON spec objects, highlighting
 * additions (green), removals (red), and changes (yellow). Collapsible by
 * default; the operator clicks "Show changes" to expand.
 *
 * Uses Tailwind classes consistent with the v2 design system and references
 * design tokens from `tokens.css`.
 */
"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { AcquisitionSpec, SourceVersionRecord } from "../../lib/admin/dataProvider";

type DiffKind = "added" | "removed" | "changed" | "unchanged";

type DiffEntry = {
  key: string;
  kind: DiffKind;
  previous: string | undefined;
  current: string | undefined;
};

/** Serialize a value for display. Arrays are shown comma-separated. */
function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "(empty)";
  if (Array.isArray(value)) return value.length === 0 ? "(empty list)" : value.join(", ");
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

/** Produce a flat key-by-key diff between two acquisition spec objects. */
function diffSpecs(previous: AcquisitionSpec, current: AcquisitionSpec): DiffEntry[] {
  const allKeys = new Set<string>([...Object.keys(previous), ...Object.keys(current)]);
  const entries: DiffEntry[] = [];

  for (const key of [...allKeys].sort()) {
    const prevVal = (previous as Record<string, unknown>)[key];
    const currVal = (current as Record<string, unknown>)[key];
    const prevDisplay = displayValue(prevVal);
    const currDisplay = displayValue(currVal);

    const prevExists = key in (previous as Record<string, unknown>);
    const currExists = key in (current as Record<string, unknown>);

    if (!prevExists && currExists) {
      entries.push({ key, kind: "added", previous: undefined, current: currDisplay });
    } else if (prevExists && !currExists) {
      entries.push({ key, kind: "removed", previous: prevDisplay, current: undefined });
    } else if (prevDisplay !== currDisplay) {
      entries.push({ key, kind: "changed", previous: prevDisplay, current: currDisplay });
    } else {
      entries.push({ key, kind: "unchanged", previous: prevDisplay, current: currDisplay });
    }
  }

  return entries;
}

const KIND_STYLES: Record<DiffKind, { row: string; label: string }> = {
  added: {
    row: "bg-[var(--status-healthy-subtle)]",
    label:
      "text-[var(--status-healthy)] bg-[var(--status-healthy-subtle)] border-[var(--status-healthy)]/30",
  },
  removed: {
    row: "bg-[var(--status-critical-subtle)]",
    label:
      "text-[var(--status-critical)] bg-[var(--status-critical-subtle)] border-[var(--status-critical)]/30",
  },
  changed: {
    row: "bg-[var(--attention-subtle)]/40",
    label: "text-[var(--attention)] bg-[var(--attention-subtle)] border-[var(--attention-border)]",
  },
  unchanged: {
    row: "",
    label: "",
  },
};

const KIND_LABELS: Record<DiffKind, string | null> = {
  added: "added",
  removed: "removed",
  changed: "changed",
  unchanged: null,
};

interface SourceVersionDiffPanelProps {
  previous: SourceVersionRecord;
  current: SourceVersionRecord;
  /** Start expanded instead of collapsed. */
  defaultOpen?: boolean;
}

export function SourceVersionDiffPanel({
  previous,
  current,
  defaultOpen = false,
}: SourceVersionDiffPanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  const entries = diffSpecs(previous.acquisition_spec, current.acquisition_spec);
  const changedCount = entries.filter((e) => e.kind !== "unchanged").length;

  return (
    <div className="rounded-[12px] border border-[var(--border)] bg-white/80 backdrop-blur-[8px] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full flex items-center justify-between gap-2 px-4 py-2.5 text-left hover:bg-[var(--brand-wash-4)] transition-colors"
      >
        <span className="flex items-center gap-2 text-[13px] font-semibold text-[var(--foreground)]">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span>
            Compare with previous
            <span className="ml-1.5 text-[11px] font-normal text-[var(--foreground-subtle)]">
              {previous.version_label} vs {current.version_label}
            </span>
          </span>
        </span>
        {changedCount > 0 ? (
          <span className="inline-flex items-center h-5 px-1.5 rounded-full text-[10px] font-semibold bg-[var(--attention-subtle)] text-[var(--attention)] border border-[var(--attention-border)]">
            {changedCount} {changedCount === 1 ? "change" : "changes"}
          </span>
        ) : (
          <span className="text-[11px] text-[var(--foreground-faint)]">No changes</span>
        )}
      </button>

      {open ? (
        <div className="border-t border-[var(--border)]">
          {/* Column headers */}
          <div className="grid grid-cols-[minmax(120px,1fr)_minmax(0,2fr)_minmax(0,2fr)_80px] gap-px bg-[var(--brand-wash-6)]">
            <div className="px-3 py-1.5 text-[10px] uppercase tracking-[0.1em] font-semibold text-[var(--foreground-faint)] bg-[var(--brand-wash-6)]">
              Field
            </div>
            <div className="px-3 py-1.5 text-[10px] uppercase tracking-[0.1em] font-semibold text-[var(--foreground-faint)] bg-[var(--brand-wash-6)]">
              Previous ({previous.version_label})
            </div>
            <div className="px-3 py-1.5 text-[10px] uppercase tracking-[0.1em] font-semibold text-[var(--foreground-faint)] bg-[var(--brand-wash-6)]">
              Current ({current.version_label})
            </div>
            <div className="px-3 py-1.5 text-[10px] uppercase tracking-[0.1em] font-semibold text-[var(--foreground-faint)] bg-[var(--brand-wash-6)]">
              Status
            </div>
          </div>

          {/* Diff rows */}
          {entries.map((entry) => {
            const style = KIND_STYLES[entry.kind];
            const label = KIND_LABELS[entry.kind];

            return (
              <div
                key={entry.key}
                className={`grid grid-cols-[minmax(120px,1fr)_minmax(0,2fr)_minmax(0,2fr)_80px] gap-px border-t border-[var(--border-faint)] ${style.row}`}
              >
                <div className="px-3 py-1.5 text-[12px] font-mono font-medium text-[var(--foreground)] truncate">
                  {entry.key}
                </div>
                <div className="px-3 py-1.5 text-[12px] font-mono text-[var(--foreground-muted)] break-words">
                  {entry.previous ?? (
                    <span className="text-[var(--foreground-ghost)] italic">--</span>
                  )}
                </div>
                <div className="px-3 py-1.5 text-[12px] font-mono text-[var(--foreground-muted)] break-words">
                  {entry.current ?? (
                    <span className="text-[var(--foreground-ghost)] italic">--</span>
                  )}
                </div>
                <div className="px-3 py-1.5 flex items-start">
                  {label ? (
                    <span
                      className={`inline-flex items-center h-[18px] px-1.5 rounded-full text-[9px] font-semibold uppercase tracking-[0.04em] border ${style.label}`}
                    >
                      {label}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}

          {entries.length === 0 ? (
            <div className="px-4 py-3 text-[12px] text-[var(--foreground-faint)]">
              Both versions have empty acquisition specs.
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
