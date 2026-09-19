"use client";

/**
 * The exact `acquisition_spec` a source version will run with.
 *
 * The versions table shows `summarizeAcquisitionSpec`, which is right for a table
 * cell and lossy on purpose. This is the panel beside it that shows everything —
 * see `acquisitionSpecView.ts` for why the lossy view alone was a problem.
 *
 * Two deliberate choices:
 *
 * Identity and scope come FIRST, above the provider's own settings. They look like
 * boilerplate and read as skippable, but `corpus_id` decides which corpus a
 * document is written into and `trust_tier` is what downstream ranking believes.
 * A wrong value there is a silent, corpus-wide defect, and the summary shows none
 * of them.
 *
 * The raw JSON stays available underneath rather than replacing the rows. The rows
 * are for reading; the JSON is what you copy into an issue or diff against a
 * blueprint, and it is also the only thing that cannot go stale if a field is
 * added to a provider spec and nobody updates a renderer.
 */

import { useMemo, useState } from "react";
import type { AcquisitionSpec } from "../../lib/admin/dataProvider";
import { CodeBlock, InlineAlert } from "../../ui/primitives";
import {
  formatSpecEntryValue,
  partitionAcquisitionSpec,
  type SpecEntry,
  unreadableSpecLines,
} from "./acquisitionSpecView";

function EntryRows({ entries }: { entries: SpecEntry[] }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[12px]">
      {entries.map((entry) => (
        <div key={entry.key} className="contents">
          <dt className="font-mono text-[var(--foreground-subtle)]">{entry.key}</dt>
          <dd className="break-all font-mono text-[var(--foreground)]">
            {formatSpecEntryValue(entry.value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Group({ title, hint, entries }: { title: string; hint: string; entries: SpecEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <section>
      <h4 className="text-[12px] font-semibold text-[var(--foreground)]">
        {title} <span className="font-normal text-[var(--foreground-subtle)]">— {hint}</span>
      </h4>
      <div className="mt-1">
        <EntryRows entries={entries} />
      </div>
    </section>
  );
}

export function AcquisitionSpecPanel({
  spec,
  specError = null,
}: {
  spec: AcquisitionSpec | null;
  /** Set when `spec` is null: why the API could not read the stored one (#953). */
  specError?: string | null;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const partitioned = useMemo(
    () => (spec === null ? null : partitionAcquisitionSpec(spec)),
    [spec],
  );

  // A spec we could not read is not an empty spec. Rendering the usual groups
  // with nothing in them would say "this version is configured with nothing",
  // which is the false statement #953 is about.
  if (partitioned === null) {
    const [headline, ...rest] = unreadableSpecLines(specError);
    return (
      <div className="space-y-3" data-testid="acquisition-spec-panel">
        <InlineAlert tone="error" testId="acquisition-spec-unreadable">
          <div className="space-y-1">
            <p className="font-semibold text-[var(--foreground)]">{headline}</p>
            {rest.map((line) => (
              <p key={line} className="text-[var(--foreground-muted)]">
                {line}
              </p>
            ))}
          </div>
        </InlineAlert>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="acquisition-spec-panel">
      <div className="text-[12px]">
        <span className="text-[var(--foreground-subtle)]">provider</span>{" "}
        <span className="font-mono font-semibold text-[var(--foreground)]">
          {partitioned.provider}
        </span>
      </div>

      <Group
        title="Identity and scope"
        hint="which corpus this writes into, and how far downstream trusts it"
        entries={partitioned.identity}
      />
      <Group
        title="Provider configuration"
        hint="what this provider will actually fetch"
        entries={partitioned.providerConfig}
      />

      <div>
        <button
          type="button"
          data-testid="acquisition-spec-raw-toggle"
          onClick={() => setShowRaw((previous) => !previous)}
          className="text-[12px] font-semibold text-[var(--brand)] underline-offset-2 hover:underline"
        >
          {showRaw ? "Hide" : "Show"} raw JSON
        </button>
        {showRaw ? <CodeBlock value={spec} /> : null}
      </div>
    </div>
  );
}
